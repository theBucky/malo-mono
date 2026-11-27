"""Build the Malo fonts: latin monospace glyphs with WenYuan Sans SC CJK glyphs at 2:1 width."""

import argparse
import io
import json
import math
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Self

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
# fonts placed by hand, which the build only reads.
UPSTREAM = ROOT / "sources" / "upstream"
CACHE = ROOT / "build"
OUTPUT = ROOT / "fonts"

VERSION = "0.1"

CJK_SCALE = 0.94
LINE_HEIGHT = 1.3
# ghostty draws box drawing itself, with lines as thick as the underline.
UNDERLINE_THICKNESS = 0.1

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
    def bold(self) -> bool:
        return self.weight >= 700

    @property
    def slug(self) -> str:
        return self.name.replace(" ", "")


STYLES = (
    Style("Regular", 400, False),
    Style("Italic", 400, True),
    Style("Bold", 700, False),
    Style("Bold Italic", 700, True),
)


@dataclass(frozen=True)
class Grid:
    """The measures of a latin font that cjk glyphs and line metrics follow."""

    upem: int
    cell: int
    # the middle of the capitals.
    midline: float
    # the horizontal shift per unit of height, zero for upright fonts.
    slant: float

    @classmethod
    def of(cls, latin: TTFont) -> Self:
        cmap = unicode_cmap(latin)
        cap = latin["glyf"][cmap[ord("H")]]
        return cls(
            upem=latin["head"].unitsPerEm,
            cell=latin["hmtx"][cmap[ord(" ")]][0],
            midline=(cap.yMin + cap.yMax) / 2,
            slant=math.tan(math.radians(-latin["post"].italicAngle)),
        )


def fetch_release(repo: str, asset: str) -> Path:
    """Download `asset` of the latest `repo` release into the cache unless a copy is there.

    `{tag}` in `asset` stands for the release tag.
    """
    dest = CACHE / asset.format(tag="latest")
    if not dest.exists():
        latest = f"https://api.github.com/repos/{repo}/releases/latest"
        with urllib.request.urlopen(latest) as response:
            tag = json.load(response)["tag_name"]
        download(f"https://github.com/{repo}/releases/download/{tag}/{asset.format(tag=tag)}", dest)
    return dest


def download(url: str, dest: Path) -> None:
    print(f"download {url}")
    CACHE.mkdir(exist_ok=True)
    urllib.request.urlretrieve(url, dest)


def unicode_cmap(font: TTFont) -> dict[int, str]:
    cmap = font.getBestCmap()
    assert cmap is not None, "every source font maps unicode"
    return cmap


def load_menlo(style: Style) -> TTFont:
    menlo = TTCollection(UPSTREAM / "Menlo.ttc")
    fonts = {font["name"].getDebugName(6): font for font in menlo.fonts}
    font = fonts[f"Menlo-{style.slug}"]
    if style.bold:
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


def load_goeist_mono(style: Style) -> TTFont:
    release = fetch_release("shadcn-labs/goeist-font", "GoeistMono-{tag}.zip")
    with zipfile.ZipFile(release) as archive:
        font = TTFont(io.BytesIO(archive.read(f"GoeistMono/ttf/GoeistMono-{style.slug}.ttf")))
    # ligatures, including the coding ligatures in ss11, draw several characters in one cell.
    features = {
        record.FeatureTag
        for table in ("GSUB", "GPOS")
        for record in font[table].table.FeatureList.FeatureRecord
    }
    options = subset.Options(
        layout_features=sorted(features - {"calt", "dlig", "liga", "ss11"}),
        name_IDs=["*"],
        glyph_names=True,
        notdef_outline=True,
        passthrough_tables=True,
    )
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=unicode_cmap(font))
    subsetter.subset(font)
    return font


def load_maple_mono(style: Style) -> TTFont:
    variant = "-Italic" if style.italic else ""
    font = TTFont(UPSTREAM / f"MapleMonoNL{variant}[wght].ttf")
    instancer.instantiateVariableFont(font, {"wght": style.weight}, inplace=True)
    # the instancer leaves a STAT table that names no regular weight, so drop the table and its names.
    del font["STAT"]
    font["name"].removeUnusedNames(font)
    return font


def load_hack(style: Style) -> TTFont:
    release = fetch_release("source-foundry/Hack", "Hack-{tag}-ttf.zip")
    with zipfile.ZipFile(release) as archive:
        font = TTFont(io.BytesIO(archive.read(f"ttf/Hack-{style.slug}.ttf")))
    # alt-hack pull request 47 adds the straight l and never merged, so pin its head.
    commit = "a80cc886817949121bee4d0fbfac363d060bac4b"
    designs = CACHE / f"alt-hack-{commit}.zip"
    if not designs.exists():
        download(f"https://github.com/source-foundry/alt-hack/archive/{commit}.zip", designs)
    cmap, glyf, hmtx = unicode_cmap(font), font["glyf"], font["hmtx"]
    with zipfile.ZipFile(designs) as archive:
        for design in ("zero-forwardslash", "i-slab", "l-slab"):
            glyphs = f"alt-hack-{commit}/glyphs/{design}/{style.slug.lower()}/"
            for glif in zipfile.Path(archive, glyphs).iterdir():
                source = SimpleNamespace()
                pen = TTGlyphPointPen(None)
                readGlyphFromString(glif.read_bytes(), source, Cu2QuPointPen(pen, max_err=1))
                glyph = pen.glyph()
                glyph.recalcBounds(glyf)
                name = cmap[source.unicodes[0]]
                glyf[name] = glyph
                hmtx[name] = (source.width, glyph.xMin)
    return font


FAMILIES = {
    "Malo": load_menlo,
    "Malokeley": load_berkeley_mono,
    "Maloist": load_goeist_mono,
    "Malople": load_maple_mono,
    "Maloha": load_hack,
}


def wenyuan_subset() -> Path:
    """WenYuan cut down to its full-width glyphs in `CJK_RANGES`."""
    path = CACHE / "wenyuan-subset.ttf"
    if path.exists():
        return path
    font = TTFont(fetch_release("takushun-wu/WenYuanFonts", "WenYuanSansSCVF.ttf"))
    print("subset wenyuan")
    options = subset.Options()
    options.drop_tables += ["BASE", "GDEF", "GPOS", "GSUB", "MVAR", "STAT", "VVAR", "vhea", "vmtx"]
    subsetter = subset.Subsetter(options)
    # half-width and combining forms do not fit a double cell, so leave them to fallback fonts.
    cmap, hmtx, upem = unicode_cmap(font), font["hmtx"], font["head"].unitsPerEm
    subsetter.populate(
        unicodes=[
            cp
            for start, end in CJK_RANGES
            for cp in range(start, end + 1)
            if cp in cmap and hmtx[cmap[cp]][0] == upem
        ]
    )
    subsetter.subset(font)
    font.save(path)
    return path


def transform_glyphs(font: TTFont, transform: Transform) -> None:
    glyf, hmtx = font["glyf"], font["hmtx"]
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if glyph.numberOfContours:
            points = transform.transformPoints(glyph.coordinates)
            glyph.coordinates = GlyphCoordinates([(round(x), round(y)) for x, y in points])
            glyph.recalcBounds(glyf)
            hmtx[name] = (hmtx[name][0], glyph.xMin)


def cjk_glyphs(weight: int, grid: Grid) -> TTFont:
    """WenYuan at `weight`, scaled into double cells of `grid`, centred on its midline, and sheared."""
    advance = 2 * grid.cell
    path = CACHE / f"wenyuan-{weight}-{grid.upem}-{advance}-{grid.midline:g}.ttf"
    if not path.exists():
        font = TTFont(wenyuan_subset())
        print(f"instantiate wenyuan {weight}")
        instancer.instantiateVariableFont(font, {"wght": weight, "ital": 0}, inplace=True)
        scale_upem(font, grid.upem)
        hmtx = font["hmtx"]
        for name in font.getGlyphOrder():
            hmtx[name] = (advance, 0)
        # wenyuan's typo metrics span the ideographic em box, which centres its hanzi.
        em_centre = (font["OS/2"].sTypoAscender + font["OS/2"].sTypoDescender) / 2
        shift_x = (advance - grid.upem * CJK_SCALE) / 2
        shift_y = grid.midline - em_centre * CJK_SCALE
        transform_glyphs(font, Transform(CJK_SCALE, 0, 0, CJK_SCALE, shift_x, shift_y))
        removeOverlaps(font)
        font.save(path)
    font = TTFont(path)
    if grid.slant:
        transform_glyphs(font, Transform(1, 0, grid.slant, 1, -grid.slant * grid.midline, 0))
    return font


def merge_glyphs(latin: TTFont, source: TTFont) -> None:
    """Map every codepoint of `source` to its glyph, over any glyph `latin` has for it."""
    added = {}
    renamed = {}
    taken = set(latin.getGlyphOrder())
    for codepoint, glyph in sorted(unicode_cmap(source).items()):
        name = f"uni{codepoint:04X}"
        added[codepoint] = renamed.setdefault(glyph, f"{name}.cjk" if name in taken else name)
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


def set_line_height(font: TTFont, grid: Grid) -> None:
    """Centre a `LINE_HEIGHT` line box on the midline of `grid`."""
    line_height = round(LINE_HEIGHT * grid.upem)
    ascent = round(grid.midline + line_height / 2)
    descent = ascent - line_height
    hhea, os2 = font["hhea"], font["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = ascent, descent, 0
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = ascent, descent, 0
    os2.usWinAscent, os2.usWinDescent = ascent, -descent


def rename(font: TTFont, family: str, style: Style, copyright_notice: str) -> None:
    postscript_name = f"{family}-{style.slug}"
    name = font["name"]
    values = {
        0: copyright_notice,
        1: family,
        2: style.name,
        3: f"{VERSION};{postscript_name}",
        4: f"{family} {style.name}",
        5: f"Version {VERSION}",
        6: postscript_name,
    }
    # keep the license and the feature names that layout tables point to.
    name.names = [
        record for record in name.names if record.nameID in (13, 14) or record.nameID > 255
    ]
    for name_id, value in values.items():
        name.setName(value, name_id, 3, 1, 0x409)
    font["head"].fontRevision = float(VERSION)

    os2 = font["OS/2"]
    os2.usWeightClass = style.weight
    regular = not (style.bold or style.italic)
    os2.fsSelection = os2.fsSelection & ~0b1100001 | style.bold << 5 | style.italic | regular << 6
    font["head"].macStyle = style.bold | style.italic << 1


def build(family: str, style: Style) -> Path:
    latin = FAMILIES[family](style)
    grid = Grid.of(latin)
    cjk = cjk_glyphs(style.weight, grid)
    copyright_notice = f"{latin['name'].getDebugName(0)} {cjk['name'].getDebugName(0)}"
    merge_glyphs(latin, cjk)
    set_line_height(latin, grid)
    latin["post"].underlineThickness = round(UNDERLINE_THICKNESS * grid.upem)
    rename(latin, family, style, copyright_notice)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT / f"{latin['name'].getDebugName(6)}.ttf"
    latin.save(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", action="append", choices=FAMILIES)
    parser.add_argument("--style", action="append", choices=[s.name for s in STYLES])
    parser.add_argument(
        "--clean",
        action="store_true",
        help="drop cached downloads and intermediate fonts, as a run without filters does",
    )
    args = parser.parse_args()
    if args.clean or not (args.family or args.style):
        shutil.rmtree(CACHE, ignore_errors=True)
    for family in args.family or FAMILIES:
        for style in STYLES:
            if not args.style or style.name in args.style:
                print(f"built {build(family, style)}")


if __name__ == "__main__":
    main()
