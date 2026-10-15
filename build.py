"""Build Malo from Menlo, or Malo Alt from Hack, with WenYuan Sans SC CJK glyphs at 2:1 width."""

import argparse
import io
import math
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from fontTools import subset
from fontTools.misc.transform import Transform
from fontTools.pens.cu2quPen import Cu2QuPointPen
from fontTools.pens.ttGlyphPen import TTGlyphPointPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ufoLib.glifLib import readGlyphFromString
from fontTools.varLib import instancer

ROOT = Path(__file__).parent
UPSTREAM = ROOT / "sources" / "upstream"
CACHE = ROOT / "build"
OUTPUT = ROOT / "fonts"

MENLO_SYSTEM = Path("/System/Library/Fonts/Menlo.ttc")
MENLO_TTC = UPSTREAM / "Menlo.ttc"
HACK_URL = "https://github.com/source-foundry/Hack/releases/download/v3.003/Hack-v3.003-ttf.zip"
HACK_ZIP = UPSTREAM / "hack" / Path(HACK_URL).name
ALT_HACK_ZERO_URL = (
    "https://raw.githubusercontent.com/source-foundry/alt-hack/"
    "9fab7328cfc208046cb7f3d713ec97a724d8219a/glyphs/u0030-forwardslash/{style}/zero.glif"
)
WENYUAN_URL = (
    "https://github.com/takushun-wu/WenYuanFonts/releases/download/v1.100/WenYuanSansSCVF.ttf"
)
WENYUAN_VF = UPSTREAM / "wenyuan" / "WenYuanSansSCVF.ttf"
WENYUAN_SUBSET = CACHE / "wenyuan-subset.ttf"

VERSION = "0.1"

CJK_SCALE = 0.94
LINE_HEIGHT = 1.3
CJK_FACE_REFERENCE = ord("国")
LATIN_CAP_REFERENCE = ord("H")

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

    @property
    def slug(self) -> str:
        return self.name.replace(" ", "")


STYLES = (
    Style("Regular", 400, False),
    Style("Italic", 400, True),
    Style("Bold", 700, False),
    Style("Bold Italic", 700, True),
)


def fetch(url: str, dest: Path) -> None:
    if dest.exists():
        return
    print(f"download {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)


def load_menlo(style: Style) -> TTFont:
    fetch(MENLO_SYSTEM.as_uri(), MENLO_TTC)
    fonts = TTCollection(MENLO_TTC).fonts
    return next(font for font in fonts if font["name"].getDebugName(6) == f"Menlo-{style.slug}")


def load_hack(style: Style) -> TTFont:
    """Hack with the forward-slash zero from alt-hack."""
    fetch(HACK_URL, HACK_ZIP)
    with zipfile.ZipFile(HACK_ZIP) as archive:
        font = TTFont(io.BytesIO(archive.read(f"ttf/Hack-{style.slug}.ttf")))
    del font["DSIG"]
    variant = style.slug.lower()
    zero = UPSTREAM / "hack" / f"zero-{variant}.glif"
    fetch(ALT_HACK_ZERO_URL.format(style=variant), zero)
    replace_glyph(font, zero)
    return font


def replace_glyph(font: TTFont, glif: Path) -> None:
    """Draw the UFO glyph in `glif` over the glyph its codepoint maps to, merging overlapping contours."""
    pen = TTGlyphPointPen(None)
    ufo_glyph = SimpleNamespace()
    cu2qu = Cu2QuPointPen(pen, max_err=font["head"].unitsPerEm / 1000)
    readGlyphFromString(glif.read_bytes(), ufo_glyph, cu2qu)
    name = font.getBestCmap()[ufo_glyph.unicodes[0]]
    font["glyf"][name] = pen.glyph()
    font["hmtx"][name] = (ufo_glyph.width, 0)
    removeOverlaps(font, [name])


def subset_wenyuan() -> None:
    if WENYUAN_SUBSET.exists():
        return
    fetch(WENYUAN_URL, WENYUAN_VF)
    print("subset wenyuan")
    font = TTFont(WENYUAN_VF)
    options = subset.Options()
    options.drop_tables += ["BASE", "GDEF", "GPOS", "GSUB", "MVAR", "STAT", "VVAR", "vhea", "vmtx"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[cp for start, end in CJK_RANGES for cp in range(start, end + 1)])
    subsetter.subset(font)
    WENYUAN_SUBSET.parent.mkdir(parents=True, exist_ok=True)
    font.save(WENYUAN_SUBSET)


def transform_glyphs(font: TTFont, transform: Transform) -> None:
    glyf, hmtx = font["glyf"], font["hmtx"]
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if glyph.numberOfContours:
            points = transform.transformPoints(glyph.coordinates)
            glyph.coordinates = GlyphCoordinates([(round(x), round(y)) for x, y in points])
            glyph.recalcBounds(glyf)
            hmtx[name] = (hmtx[name][0], glyph.xMin)


def ink_midline(font: TTFont, codepoint: int) -> float:
    glyf = font["glyf"]
    glyph = glyf[font.getBestCmap()[codepoint]]
    glyph.recalcBounds(glyf)
    return (glyph.yMin + glyph.yMax) / 2


def cjk_glyphs(latin: TTFont, midline: float, style: Style) -> TTFont:
    """WenYuan scaled into double cells of `latin`, centred on `midline`, and sheared to its italic angle."""
    upem = latin["head"].unitsPerEm
    advance = 2 * latin["hmtx"][latin.getBestCmap()[ord(" ")]][0]
    path = CACHE / f"wenyuan-{style.weight}-{upem}-{advance}-{midline:g}.ttf"
    if not path.exists():
        print(f"instantiate wenyuan {style.weight}")
        font = TTFont(WENYUAN_SUBSET)
        instancer.instantiateVariableFont(font, {"wght": style.weight, "ital": 0}, inplace=True)
        scale_upem(font, upem)
        hmtx = font["hmtx"]
        for name in font.getGlyphOrder():
            hmtx[name] = (advance, 0)
        shift_x = (advance - upem * CJK_SCALE) / 2
        shift_y = midline - ink_midline(font, CJK_FACE_REFERENCE) * CJK_SCALE
        transform_glyphs(font, Transform(CJK_SCALE, 0, 0, CJK_SCALE, shift_x, shift_y))
        removeOverlaps(font)
        font.save(path)
    font = TTFont(path)
    if style.italic:
        skew = math.tan(math.radians(-latin["post"].italicAngle))
        transform_glyphs(font, Transform(1, 0, skew, 1, -skew * midline, 0))
    return font


def merge_cjk(latin: TTFont, cjk: TTFont) -> None:
    """Map every CJK codepoint to the double-cell glyph, over any half-width Latin glyph."""
    added = {}
    renamed = {}
    for codepoint, glyph in sorted(cjk.getBestCmap().items()):
        added[codepoint] = renamed.setdefault(glyph, f"uni{codepoint:04X}")
    glyph_order = latin.getGlyphOrder() + list(renamed.values())
    for old, new in renamed.items():
        latin["glyf"][new] = cjk["glyf"][old]
        latin["hmtx"][new] = cjk["hmtx"][old]
    latin.setGlyphOrder(glyph_order)
    for table in latin["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(added)
    latin["OS/2"].recalcUnicodeRanges(latin)
    latin["OS/2"].recalcCodePageRanges(latin)


def set_line_height(font: TTFont, midline: float) -> None:
    """Centre a `LINE_HEIGHT` line box on `midline`."""
    line_height = round(LINE_HEIGHT * font["head"].unitsPerEm)
    ascent = round(midline + line_height / 2)
    descent = ascent - line_height
    hhea, os2 = font["hhea"], font["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = ascent, descent, 0
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = ascent, descent, 0
    os2.usWinAscent, os2.usWinDescent = ascent, -descent


def strip_hinting(font: TTFont) -> None:
    for tag in ("cvt ", "fpgm", "prep", "hdmx", "gasp", "TTFA"):
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


def build(latin: TTFont, family: str, style: Style) -> Path:
    midline = ink_midline(latin, LATIN_CAP_REFERENCE)
    cjk = cjk_glyphs(latin, midline, style)
    merge_cjk(latin, cjk)
    set_line_height(latin, midline)
    strip_hinting(latin)
    rename(latin, family, style, cjk["name"].getDebugName(0))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT / f"{latin['name'].getDebugName(6)}.ttf"
    latin.save(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", action="append", choices=[s.name for s in STYLES])
    parser.add_argument("--alt", action="store_true", help="build Malo Alt with Hack Latin glyphs")
    parser.add_argument("--clean", action="store_true", help="drop cached intermediate fonts")
    args = parser.parse_args()
    if args.clean:
        shutil.rmtree(CACHE, ignore_errors=True)
    family, load_latin = ("Malo Alt", load_hack) if args.alt else ("Malo", load_menlo)
    subset_wenyuan()
    for style in STYLES:
        if args.style and style.name not in args.style:
            continue
        print(f"built {build(load_latin(style), family, style)}")


if __name__ == "__main__":
    main()
