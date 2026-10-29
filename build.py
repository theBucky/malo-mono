"""Build Malo from Menlo, or Malo Alt from Berkeley Mono, with WenYuan Sans SC CJK glyphs at 2:1 width."""

import argparse
import math
import shutil
import urllib.request
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

MENLO_URL = "file:///System/Library/Fonts/Menlo.ttc"
MENLO_TTC = UPSTREAM / "Menlo.ttc"
WENYUAN_URL = (
    "https://github.com/takushun-wu/WenYuanFonts/releases/download/v1.100/WenYuanSansSCVF.ttf"
)
WENYUAN_VF = UPSTREAM / "wenyuan" / "WenYuanSansSCVF.ttf"
WENYUAN_SUBSET = CACHE / "wenyuan-subset.ttf"

VERSION = "0.1"

CJK_SCALE = 0.94
LINE_HEIGHT = 1.3
# ghostty draws box drawing itself, with lines as thick as the underline.
UNDERLINE_THICKNESS = 0.1
CJK_FACE_REFERENCE = ord("国")
LATIN_CAP_REFERENCE = ord("H")
BOX_DRAWING = range(0x2500, 0x2580)

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
    fetch(MENLO_URL, MENLO_TTC)
    fonts = {font["name"].getDebugName(6): font for font in TTCollection(MENLO_TTC).fonts}
    font = fonts[f"Menlo-{style.slug}"]
    if style.weight >= 700:
        # menlo bold has no box drawing, so take the upright regular glyphs as menlo italic does.
        # their hinting calls into the regular font program, so drop it.
        regular = fonts["Menlo-Regular"]
        options = subset.Options(hinting=False)
        options.drop_tables += ["feat", "meta", "morx"]
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=BOX_DRAWING)
        subsetter.subset(regular)
        merge_glyphs(font, regular)
    return font


def load_berkeley_mono(style: Style) -> TTFont:
    variant = style.name.replace("Italic", "Oblique").replace(" ", "-")
    return TTFont(UPSTREAM / f"BerkeleyMono-{variant}.ttf")


def subset_wenyuan() -> None:
    if WENYUAN_SUBSET.exists():
        return
    fetch(WENYUAN_URL, WENYUAN_VF)
    print("subset wenyuan")
    font = TTFont(WENYUAN_VF)
    options = subset.Options()
    options.drop_tables += ["BASE", "GDEF", "GPOS", "GSUB", "MVAR", "STAT", "VVAR", "vhea", "vmtx"]
    subsetter = subset.Subsetter(options)
    # half-width and combining forms do not fit a double cell, so leave them to fallback fonts.
    cmap, hmtx, upem = font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm
    subsetter.populate(
        unicodes=[
            cp
            for start, end in CJK_RANGES
            for cp in range(start, end + 1)
            if cp in cmap and hmtx[cmap[cp]][0] == upem
        ]
    )
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


def merge_glyphs(latin: TTFont, source: TTFont) -> None:
    """Map every codepoint of `source` to its glyph, over any glyph `latin` has for it."""
    added = {}
    renamed = {}
    for codepoint, glyph in sorted(source.getBestCmap().items()):
        added[codepoint] = renamed.setdefault(glyph, f"uni{codepoint:04X}")
    glyph_order = latin.getGlyphOrder() + list(renamed.values())
    if "hdmx" in latin:
        # read before inserting glyphs, which extends the glyph order hdmx decompiles against.
        upem, hdmx = latin["head"].unitsPerEm, latin["hdmx"].hdmx
        for ppem, widths in hdmx.items():
            hdmx[ppem] = dict(widths) | {
                new: round(source["hmtx"][old][0] * ppem / upem) for old, new in renamed.items()
            }
    for old, new in renamed.items():
        latin["glyf"][new] = source["glyf"][old]
        latin["hmtx"][new] = source["hmtx"][old]
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
    merge_glyphs(latin, cjk)
    set_line_height(latin, midline)
    latin["post"].underlineThickness = round(UNDERLINE_THICKNESS * latin["head"].unitsPerEm)
    rename(latin, family, style, cjk["name"].getDebugName(0))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT / f"{latin['name'].getDebugName(6)}.ttf"
    latin.save(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", action="append", choices=[s.name for s in STYLES])
    parser.add_argument("--alt", action="store_true", help="build Malo Alt from Berkeley Mono")
    parser.add_argument("--clean", action="store_true", help="drop cached intermediate fonts")
    args = parser.parse_args()
    if args.clean:
        shutil.rmtree(CACHE, ignore_errors=True)
    family, load_latin = ("Malo Alt", load_berkeley_mono) if args.alt else ("Malo", load_menlo)
    subset_wenyuan()
    for style in STYLES:
        if args.style and style.name not in args.style:
            continue
        print(f"built {build(load_latin(style), family, style)}")


if __name__ == "__main__":
    main()
