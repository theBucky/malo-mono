"""Build Malo: Menlo Latin glyphs plus WenYuan Sans SC CJK glyphs at 2:1 width."""

import argparse
import math
import shutil
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fontTools import subset
from fontTools.misc.transform import Transform
from fontTools.pens.ttGlyphPen import TTGlyphPen
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
WENYUAN_URL = (
    "https://github.com/takushun-wu/WenYuanFonts/releases/download/v1.100/WenYuanSansSCVF.ttf"
)
WENYUAN_VF = UPSTREAM / "wenyuan" / "WenYuanSansSCVF.ttf"
WENYUAN_SUBSET = CACHE / "wenyuan-subset.ttf"

FAMILY = "Malo"
VERSION = "0.1"

UPEM = 2048
LATIN_ADVANCE = 1233
CAP_HEIGHT = 1493
X_HEIGHT = 1120
LINE_HEIGHT = 1.4
CJK_ADVANCE = 2 * LATIN_ADVANCE
CJK_SCALE = 0.95
ITALIC_ANGLE = 11
ITALIC_PIVOT_Y = CAP_HEIGHT / 2
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
    def menlo_name(self) -> str:
        return f"Menlo-{self.name.replace(' ', '')}"

    @property
    def postscript_name(self) -> str:
        return f"{FAMILY}-{self.name.replace(' ', '')}"


STYLES = (
    Style("Regular", 400, False, latin_weight=450),
    Style("Italic", 400, True, latin_weight=450),
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


def ensure_sources() -> None:
    if not MENLO_TTC.exists():
        MENLO_TTC.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(MENLO_SYSTEM, MENLO_TTC)
    download(WENYUAN_URL, WENYUAN_VF)


def load_menlo(style: Style) -> TTFont:
    fonts = TTCollection(MENLO_TTC).fonts
    return next(font for font in fonts if font["name"].getDebugName(6) == style.menlo_name)


def subset_wenyuan() -> None:
    if WENYUAN_SUBSET.exists():
        return
    print("subset wenyuan")
    font = TTFont(WENYUAN_VF)
    options = subset.Options()
    options.layout_features = []
    options.drop_tables += ["BASE", "GDEF", "GPOS", "GSUB", "MVAR", "STAT", "VVAR", "vhea", "vmtx"]
    options.notdef_outline = True
    options.name_IDs = ["*"]
    options.recalc_bounds = True
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
    """Thicken stems by `weight_gain` weight units; edges below the baseline or above the x-height move back so every alignment height stays put."""
    strength = tuple(gain * weight_gain for gain in MENLO_STEM_GAIN_PER_WEIGHT)
    half_y = strength[1] / 2
    band_bottom, band_top = -half_y, X_HEIGHT + half_y

    def pin(y: float) -> float:
        if y <= band_bottom:
            return y + half_y
        if y >= band_top:
            return y - half_y
        return (y - band_bottom) * X_HEIGHT / (band_top - band_bottom)

    map_contours(
        font, lambda contour: [(x, pin(y)) for x, y in embolden_contour(contour, strength)]
    )


def decompose_composites(font: TTFont) -> None:
    glyf = font["glyf"]
    glyph_set = font.getGlyphSet()
    for name in font.getGlyphOrder():
        if glyf[name].isComposite():
            pen = TTGlyphPen(glyph_set)
            glyph_set[name].draw(pen)
            glyf[name] = pen.glyph()


def map_contours(font: TTFont, reshape: Callable) -> None:
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


def skew_glyphs(font: TTFont) -> None:
    skew = math.tan(math.radians(ITALIC_ANGLE))
    map_contours(font, Transform(1, 0, skew, 1, -skew * ITALIC_PIVOT_Y, 0).transformPoints)


def cjk_upright(weight: int) -> TTFont:
    path = CACHE / f"wenyuan-{weight}.ttf"
    if not path.exists():
        print(f"instantiate wenyuan {weight}")
        font = TTFont(WENYUAN_SUBSET)
        instancer.instantiateVariableFont(
            font, {"wght": weight, "ital": 0}, inplace=True, optimize=False
        )
        scale_upem(font, UPEM)
        decompose_composites(font)
        hmtx = font["hmtx"]
        for name in font.getGlyphOrder():
            hmtx[name] = (CJK_ADVANCE, 0)
        shift_x = (CJK_ADVANCE - UPEM * CJK_SCALE) / 2
        map_contours(font, Transform(CJK_SCALE, 0, 0, CJK_SCALE, shift_x, 0).transformPoints)
        removeOverlaps(font)
        font.save(path)
    return TTFont(path)


def merge_cjk(latin: TTFont, cjk: TTFont) -> None:
    latin_cmap = latin.getBestCmap()
    new_codepoints = {cp: g for cp, g in cjk.getBestCmap().items() if cp not in latin_cmap}
    renamed = {g: f"cjk{i:05d}" for i, g in enumerate(sorted(set(new_codepoints.values())))}

    glyph_order = latin.getGlyphOrder() + list(renamed.values())
    for old, new in renamed.items():
        latin["glyf"][new] = cjk["glyf"][old]
        latin["hmtx"][new] = cjk["hmtx"][old]
    latin.setGlyphOrder(glyph_order)
    latin["maxp"].numGlyphs = len(glyph_order)
    for table in latin["cmap"].tables:
        if table.isUnicode():
            table.cmap.update({cp: renamed[g] for cp, g in new_codepoints.items()})

    latin["hhea"].recalc(latin)
    latin["OS/2"].recalcUnicodeRanges(latin)
    latin["OS/2"].recalcCodePageRanges(latin)


def strip_hinting(font: TTFont) -> None:
    for tag in ("cvt ", "fpgm", "prep", "hdmx"):
        del font[tag]
    glyf = font["glyf"]
    for name in font.getGlyphOrder():
        glyf[name].removeHinting()
    # head flags 2-4 describe how instructions affect scaling and advances.
    font["head"].flags &= ~0b11100


def set_line_height(font: TTFont) -> None:
    hhea = font["hhea"]
    pad = math.ceil((LINE_HEIGHT * UPEM - (hhea.ascent - hhea.descent)) / 2)
    ascent, descent = hhea.ascent + pad, hhea.descent - pad
    hhea.ascent, hhea.descent, hhea.lineGap = ascent, descent, 0
    os2 = font["OS/2"]
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = ascent, descent, 0
    os2.usWinAscent, os2.usWinDescent = ascent, -descent


def rename(font: TTFont, style: Style, cjk_copyright: str) -> None:
    name = font["name"]
    values = {
        0: f"{name.getDebugName(0)} {cjk_copyright}",
        1: FAMILY,
        2: style.name,
        3: f"{VERSION};{style.postscript_name}",
        4: f"{FAMILY} {style.name}",
        5: f"Version {VERSION}",
        6: style.postscript_name,
    }
    name.names = []
    for name_id, value in values.items():
        name.setName(value, name_id, 3, 1, 0x409)
    font["head"].fontRevision = float(VERSION)


def build(style: Style) -> Path:
    latin = load_menlo(style)
    if style.latin_weight != style.weight:
        embolden(latin, style.latin_weight - style.weight)
    cjk = cjk_upright(style.weight)
    if style.italic:
        skew_glyphs(cjk)
    merge_cjk(latin, cjk)
    set_line_height(latin)
    strip_hinting(latin)
    rename(latin, style, cjk["name"].getDebugName(0))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT / f"{style.postscript_name}.ttf"
    latin.save(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", action="append", choices=[s.name for s in STYLES])
    parser.add_argument("--clean", action="store_true", help="drop cached intermediate fonts")
    args = parser.parse_args()
    if args.clean:
        shutil.rmtree(CACHE, ignore_errors=True)
    ensure_sources()
    subset_wenyuan()
    for style in STYLES:
        if args.style and style.name not in args.style:
            continue
        print(f"built {build(style)}")


if __name__ == "__main__":
    main()
