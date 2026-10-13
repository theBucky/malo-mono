"""Build Malo: Meslo LG M Latin glyphs plus WenYuan Sans SC CJK glyphs at 2:1 width."""

import argparse
import math
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from fontTools import subset
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib import instancer

ROOT = Path(__file__).parent
UPSTREAM = ROOT / "sources" / "upstream"
CACHE = ROOT / "build"
OUTPUT = ROOT / "fonts"

MESLO_URL = "https://github.com/andreberg/Meslo-Font/raw/master/dist/v1.2.1/Meslo%20LG%20v1.2.1.zip"
MESLO_ZIP = UPSTREAM / "meslo" / "meslo-lg-v1.2.1.zip"
MESLO_DIR = UPSTREAM / "meslo" / "extracted" / "Meslo LG v1.2.1"
WENYUAN_URL = (
    "https://github.com/takushun-wu/WenYuanFonts/releases/download/v1.100/WenYuanSansSCVF.ttf"
)
WENYUAN_VF = UPSTREAM / "wenyuan" / "WenYuanSansSCVF.ttf"
WENYUAN_SUBSET = CACHE / "wenyuan-subset.ttf"

FAMILY = "Malo"
VERSION = "0.1"

# Meslo LG M: 2048 upem, 1.36 em line height, every glyph advances 1233, italic leans 11 degrees around half the cap height.
UPEM = 2048
CJK_ADVANCE = 2 * 1233
CJK_SCALE = (0.95, 0.95)
ITALIC_ANGLE = 11
ITALIC_PIVOT_Y = 1493 / 2

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
    def meslo_path(self) -> Path:
        return MESLO_DIR / f"MesloLGM-{self.name.replace(' ', '')}.ttf"

    @property
    def postscript_name(self) -> str:
        return f"{FAMILY}-{self.name.replace(' ', '')}"


STYLES = (
    Style("Regular", 400, False),
    Style("Italic", 400, True),
    Style("Bold", 700, False),
    Style("Bold Italic", 700, True),
)


def download(url: str, dest: Path) -> None:
    if dest.exists():
        return
    print(f"download {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, dest.open("wb") as file:
        shutil.copyfileobj(response, file)


def ensure_sources() -> None:
    download(MESLO_URL, MESLO_ZIP)
    download(WENYUAN_URL, WENYUAN_VF)
    if not MESLO_DIR.is_dir():
        with zipfile.ZipFile(MESLO_ZIP) as archive:
            archive.extractall(MESLO_DIR.parent)


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


def decompose_composites(font: TTFont) -> None:
    glyf = font["glyf"]
    glyph_set = font.getGlyphSet()
    for name in font.getGlyphOrder():
        if glyf[name].isComposite():
            pen = TTGlyphPen(glyph_set)
            glyph_set[name].draw(pen)
            glyf[name] = pen.glyph()


def fit_cjk_glyphs(font: TTFont) -> None:
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    scale_x, scale_y = CJK_SCALE
    shift_x = (CJK_ADVANCE - UPEM * scale_x) / 2
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if glyph.numberOfContours > 0:
            glyph.coordinates.scale((scale_x, scale_y))
            glyph.coordinates.translate((shift_x, 0))
            glyph.recalcBounds(glyf)
        hmtx[name] = (CJK_ADVANCE, getattr(glyph, "xMin", 0))


def skew_glyphs(font: TTFont) -> None:
    skew = math.tan(math.radians(ITALIC_ANGLE))
    glyf = font["glyf"]
    hmtx = font["hmtx"]
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if glyph.numberOfContours <= 0:
            continue
        glyph.coordinates.transform(((1, 0), (skew, 1), (-skew * ITALIC_PIVOT_Y, 0)))
        glyph.recalcBounds(glyf)
        advance, _ = hmtx[name]
        hmtx[name] = (advance, glyph.xMin)


def cjk_upright(weight: int) -> Path:
    path = CACHE / f"wenyuan-{weight}.ttf"
    if path.exists():
        return path
    print(f"instantiate wenyuan {weight}")
    font = TTFont(WENYUAN_SUBSET)
    instancer.instantiateVariableFont(
        font, {"wght": weight, "ital": 0}, inplace=True, optimize=False
    )
    scale_upem(font, UPEM)
    decompose_composites(font)
    fit_cjk_glyphs(font)
    removeOverlaps(font)
    font.save(path)
    return path


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
    for tag in ("cvt ", "fpgm", "prep", "gasp", "hdmx", "LTSH", "VDMX"):
        if tag in font:
            del font[tag]
    glyf = font["glyf"]
    for name in font.getGlyphOrder():
        glyf[name].removeHinting()
    # head flags 2-4 describe how instructions affect scaling and advances.
    font["head"].flags &= ~0b11100


def rename(font: TTFont, style: Style, cjk_copyright: str) -> None:
    name = font["name"]
    name.removeNames(platformID=1)
    values = {
        0: f"{name.getDebugName(0)} {cjk_copyright}",
        1: FAMILY,
        2: style.name,
        3: f"{VERSION};{style.postscript_name}",
        4: f"{FAMILY} {style.name}",
        5: f"Version {VERSION}",
        6: style.postscript_name,
    }
    for record in name.names:
        if record.nameID in values:
            record.string = values[record.nameID]
    font["head"].fontRevision = float(VERSION)


def build(style: Style) -> Path:
    latin = TTFont(style.meslo_path)
    cjk = TTFont(cjk_upright(style.weight))
    if style.italic:
        skew_glyphs(cjk)
    merge_cjk(latin, cjk)
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
