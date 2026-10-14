"""Build Malo: Latin glyphs from Menlo (Malo) or Geist Mono (Malo V2) plus WenYuan Sans SC CJK glyphs at 2:1 width."""

import argparse
import io
import math
import shutil
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fontTools import subset
from fontTools.misc.transform import Transform
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.varLib import instancer

ROOT = Path(__file__).parent
UPSTREAM = ROOT / "sources" / "upstream"
CACHE = ROOT / "build"
OUTPUT = ROOT / "fonts"

MENLO_SYSTEM = Path("/System/Library/Fonts/Menlo.ttc")
MENLO_TTC = UPSTREAM / "Menlo.ttc"
GEIST_URL = "https://github.com/vercel/geist-font/releases/download/v1.7.2/geist-font-v1.7.2.zip"
GEIST_ZIP = UPSTREAM / "geist" / Path(GEIST_URL).name
WENYUAN_URL = (
    "https://github.com/takushun-wu/WenYuanFonts/releases/download/v1.100/WenYuanSansSCVF.ttf"
)
WENYUAN_VF = UPSTREAM / "wenyuan" / "WenYuanSansSCVF.ttf"
WENYUAN_SUBSET = CACHE / "wenyuan-subset.ttf"

VERSION = "0.1"

CJK_SCALE = 0.95
# The ink box of this glyph stands in for the CJK face when centring.
CJK_FACE_REFERENCE = ord("国")
# Measured from Menlo Regular (400) to Bold (700): vertical "n" stems grow 107 units, the horizontal "H" bar 90.
MENLO_STEM_GAIN_PER_WEIGHT = (107 / 300, 90 / 300)

CJK_RANGES = (
    (0x2460, 0x24FF),
    (0x2E80, 0x2EFF),
    (0x2F00, 0x2FDF),
    (0x2FF0, 0x2FFF),
    (0x3000, 0x303F),
    (0x3040, 0x30FF),
    (0x3100, 0x312F),
    (0x31A0, 0x31EF),
    (0x3200, 0x33FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE6F),
    (0xFF00, 0xFFEF),
)


@dataclass(frozen=True)
class Style:
    name: str
    weight: int
    italic: bool
    latin_weight: int

    @property
    def slug(self) -> str:
        return self.name.replace(" ", "")


STYLES = (
    Style("Regular", 400, False, latin_weight=420),
    Style("Italic", 400, True, latin_weight=420),
    Style("Bold", 700, False, latin_weight=700),
    Style("Bold Italic", 700, True, latin_weight=700),
)


def download(url: str, dest: Path) -> None:
    if dest.exists():
        return
    print(f"download {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, dest.open("wb") as file:
        shutil.copyfileobj(response, file)


def load_menlo(style: Style) -> TTFont:
    if not MENLO_TTC.exists():
        MENLO_TTC.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(MENLO_SYSTEM, MENLO_TTC)
    fonts = TTCollection(MENLO_TTC).fonts
    font = next(font for font in fonts if font["name"].getDebugName(6) == f"Menlo-{style.slug}")
    if style.latin_weight != style.weight:
        embolden(font, style.latin_weight - style.weight)
    return font


def load_geist_mono(style: Style) -> TTFont:
    download(GEIST_URL, GEIST_ZIP)
    member = f"GeistMono{'-Italic' if style.italic else ''}[wght].ttf"
    with zipfile.ZipFile(GEIST_ZIP) as archive:
        font = TTFont(io.BytesIO(archive.read(f"geist-font/GeistMono/variable/{member}")))
    instancer.instantiateVariableFont(font, {"wght": style.latin_weight}, inplace=True)
    return font


FAMILIES = {"Malo": load_menlo, "Malo V2": load_geist_mono}


def subset_wenyuan() -> None:
    if WENYUAN_SUBSET.exists():
        return
    print("subset wenyuan")
    font = TTFont(WENYUAN_VF)
    options = subset.Options()
    options.drop_tables += ["BASE", "GDEF", "GPOS", "GSUB", "MVAR", "STAT", "VVAR", "vhea", "vmtx"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[cp for start, end in CJK_RANGES for cp in range(start, end + 1)])
    subsetter.subset(font)
    WENYUAN_SUBSET.parent.mkdir(parents=True, exist_ok=True)
    font.save(WENYUAN_SUBSET)


def embolden_contour(points: list, strength: tuple) -> list:
    """Port of FreeType FT_Outline_EmboldenXY for a clockwise TrueType contour, minus its rightward shift, so stems grow by `strength` and stay centred."""
    half_x, half_y = strength[0] / 2, strength[1] / 2
    count = len(points)

    def neighbour(i: int, step: int) -> tuple | None:
        others = (points[(i + step * k) % count] for k in range(1, count))
        return next((point for point in others if point != points[i]), None)

    result = []
    for i, (x, y) in enumerate(points):
        prev, after = neighbour(i, -1), neighbour(i, 1)
        if prev is None:
            result.append((x, y))
            continue
        len_in = math.hypot(x - prev[0], y - prev[1])
        len_out = math.hypot(after[0] - x, after[1] - y)
        in_x, in_y = (x - prev[0]) / len_in, (y - prev[1]) / len_in
        out_x, out_y = (after[0] - x) / len_out, (after[1] - y) / len_out
        d = in_x * out_x + in_y * out_y
        if d <= -0.9375:
            result.append((x, y))
            continue
        d += 1
        normal_x, normal_y = -(in_y + out_y), in_x + out_x
        q = out_y * in_x - out_x * in_y
        limit = min(len_in, len_out)
        shift_x = normal_x * (half_x / d if half_x * q <= limit * d else limit / q)
        shift_y = normal_y * (half_y / d if half_y * q <= limit * d else limit / q)
        result.append((x + shift_x, y + shift_y))
    return result


def embolden(font: TTFont, weight_gain: int) -> None:
    """Thicken Menlo stems by `weight_gain` weight units; edges below the baseline or above the x-height move back so every alignment height stays put."""
    strength = tuple(gain * weight_gain for gain in MENLO_STEM_GAIN_PER_WEIGHT)
    half_y = strength[1] / 2
    x_height = font["OS/2"].sxHeight
    band_bottom, band_top = -half_y, x_height + half_y

    def pin(y: float) -> float:
        if y <= band_bottom:
            return y + half_y
        if y >= band_top:
            return y - half_y
        return (y - band_bottom) * x_height / (band_top - band_bottom)

    map_contours(
        font, lambda contour: [(x, pin(y)) for x, y in embolden_contour(contour, strength)]
    )


def map_contours(font: TTFont, reshape: Callable) -> None:
    """Reshape every simple glyph contour by contour, then refresh bounds and left side bearings, composites included."""
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    names = font.getGlyphOrder()
    for name in names:
        glyph = glyf[name]
        if glyph.numberOfContours > 0:
            starts = [0, *(end + 1 for end in glyph.endPtsOfContours[:-1])]
            glyph.coordinates = GlyphCoordinates(
                [
                    (round(x), round(y))
                    for start, end in zip(starts, glyph.endPtsOfContours)
                    for x, y in reshape(list(glyph.coordinates[start : end + 1]))
                ]
            )
    for name in names:
        glyph = glyf[name]
        if glyph.numberOfContours:
            glyph.recalcBounds(glyf)
            hmtx[name] = (hmtx[name][0], glyph.xMin)


def cjk_glyphs(latin: TTFont, family: str, style: Style) -> TTFont:
    """WenYuan scaled into double cells of `latin`, centred on half its cap height, and sheared to its italic angle."""
    centre_y = latin["OS/2"].sCapHeight / 2
    path = CACHE / f"wenyuan-{family.replace(' ', '')}-{style.weight}.ttf"
    if not path.exists():
        print(f"instantiate wenyuan {style.weight} for {family}")
        upem = latin["head"].unitsPerEm
        advance = 2 * latin["hmtx"]["space"][0]
        font = TTFont(WENYUAN_SUBSET)
        instancer.instantiateVariableFont(font, {"wght": style.weight, "ital": 0}, inplace=True)
        scale_upem(font, upem)
        hmtx = font["hmtx"]
        for name in font.getGlyphOrder():
            hmtx[name] = (advance, 0)
        glyf = font["glyf"]
        reference = glyf[font.getBestCmap()[CJK_FACE_REFERENCE]]
        reference.recalcBounds(glyf)
        shift_x = (advance - upem * CJK_SCALE) / 2
        shift_y = centre_y - (reference.yMin + reference.yMax) / 2 * CJK_SCALE
        map_contours(font, Transform(CJK_SCALE, 0, 0, CJK_SCALE, shift_x, shift_y).transformPoints)
        removeOverlaps(font)
        font.save(path)
    font = TTFont(path)
    if style.italic:
        skew = math.tan(math.radians(-latin["post"].italicAngle))
        map_contours(font, Transform(1, 0, skew, 1, -skew * centre_y, 0).transformPoints)
    return font


def merge_cjk(latin: TTFont, cjk: TTFont) -> None:
    """Map every CJK codepoint to the double-cell glyph, over any half-width glyph the Latin font had."""
    taken = set(latin.getGlyphOrder())
    added = {}
    renamed = {}
    for codepoint, glyph in sorted(cjk.getBestCmap().items()):
        name = f"uni{codepoint:04X}"
        added[codepoint] = renamed.setdefault(glyph, name if name not in taken else f"{name}.cjk")
    glyph_order = latin.getGlyphOrder() + list(renamed.values())
    for old, new in renamed.items():
        latin["glyf"][new] = cjk["glyf"][old]
        latin["hmtx"][new] = cjk["hmtx"][old]
    latin.setGlyphOrder(glyph_order)
    for table in latin["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(added)

    ascent, descent = cjk["hhea"].ascent, cjk["hhea"].descent
    hhea, os2 = latin["hhea"], latin["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = ascent, descent, 0
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = ascent, descent, 0
    os2.usWinAscent, os2.usWinDescent = ascent, -descent
    os2.recalcUnicodeRanges(latin)
    os2.recalcCodePageRanges(latin)


def strip_hinting(font: TTFont) -> None:
    for tag in ("cvt ", "fpgm", "prep", "hdmx"):
        if tag in font:
            del font[tag]
    glyf = font["glyf"]
    for name in font.getGlyphOrder():
        glyf[name].removeHinting()
    # head flags 2-4 describe how instructions affect scaling and advances.
    font["head"].flags &= ~0b11100


def rename(font: TTFont, family: str, style: Style, cjk_copyright: str) -> None:
    postscript_name = f"{family.replace(' ', '')}-{style.slug}"
    name = font["name"]
    values = {
        0: f"{name.getDebugName(0)} {cjk_copyright}",
        1: family,
        2: style.name,
        3: f"{VERSION};{postscript_name}",
        4: f"{family} {style.name}",
        5: f"Version {VERSION}",
        6: postscript_name,
    }
    name.names = [record for record in name.names if record.nameID in (13, 14)]
    for name_id, value in values.items():
        name.setName(value, name_id, 3, 1, 0x409)
    font["head"].fontRevision = float(VERSION)

    bold, italic = style.weight >= 700, style.italic
    os2 = font["OS/2"]
    os2.usWeightClass = style.weight
    os2.fsSelection = (
        os2.fsSelection & ~0b1100001 | bold << 5 | italic | (not bold and not italic) << 6
    )
    font["head"].macStyle = bold | italic << 1


def build(family: str, style: Style) -> Path:
    latin = FAMILIES[family](style)
    cjk = cjk_glyphs(latin, family, style)
    merge_cjk(latin, cjk)
    strip_hinting(latin)
    rename(latin, family, style, cjk["name"].getDebugName(0))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT / f"{latin['name'].getDebugName(6)}.ttf"
    latin.save(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", action="append", choices=list(FAMILIES))
    parser.add_argument("--style", action="append", choices=[s.name for s in STYLES])
    parser.add_argument("--clean", action="store_true", help="drop cached intermediate fonts")
    args = parser.parse_args()
    if args.clean:
        shutil.rmtree(CACHE, ignore_errors=True)
    download(WENYUAN_URL, WENYUAN_VF)
    subset_wenyuan()
    for family in FAMILIES:
        if args.family and family not in args.family:
            continue
        for style in STYLES:
            if args.style and style.name not in args.style:
                continue
            print(f"built {build(family, style)}")


if __name__ == "__main__":
    main()
