"""Build Malo: Hack Latin glyphs with alt-hack alternates, plus WenYuan Sans SC CJK glyphs at 2:1 width."""

import argparse
import math
import shutil
import subprocess
import sys
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

HACK_URL = "https://github.com/source-foundry/Hack/archive/refs/tags/v3.003.zip"
HACK_ZIP = UPSTREAM / "hack" / "hack-v3.003.zip"
HACK_DIR = UPSTREAM / "hack" / "Hack-3.003"
ALT_HACK_COMMIT = "9fab7328cfc208046cb7f3d713ec97a724d8219a"
ALT_HACK_URL = f"https://github.com/source-foundry/alt-hack/archive/{ALT_HACK_COMMIT}.zip"
ALT_HACK_ZIP = UPSTREAM / "hack" / "alt-hack.zip"
ALT_HACK_DIR = UPSTREAM / "hack" / f"alt-hack-{ALT_HACK_COMMIT}"
WENYUAN_URL = (
    "https://github.com/takushun-wu/WenYuanFonts/releases/download/v1.100/WenYuanSansSCVF.ttf"
)
WENYUAN_VF = UPSTREAM / "wenyuan" / "WenYuanSansSCVF.ttf"
WENYUAN_SUBSET = CACHE / "wenyuan-subset.ttf"

FAMILY = "Malo"
VERSION = "0.1"

# alt-hack glyph sets: slashed zero, and the flat DejaVu/Menlo foot for i and its accented forms.
ALTERNATES = ("u0030-forwardslash", "*-slab")

# Hack: 2048 upem, every glyph advances 1233, italic leans 11 degrees around half the cap height.
UPEM = 2048
CJK_ADVANCE = 2 * 1233
CJK_SCALE = (0.95, 0.95)
ITALIC_ANGLE = 11
ITALIC_PIVOT_Y = 1493 / 2

# Line metrics of Meslo LG S: 2584 units per line instead of Hack's 2384.
LINE_ASCENT = 2001
LINE_DESCENT = 583

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

    @property
    def postscript_name(self) -> str:
        return f"{FAMILY}-{self.slug}"


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
    download(HACK_URL, HACK_ZIP)
    download(ALT_HACK_URL, ALT_HACK_ZIP)
    download(WENYUAN_URL, WENYUAN_VF)
    for archive, target in ((HACK_ZIP, HACK_DIR), (ALT_HACK_ZIP, ALT_HACK_DIR)):
        if not target.is_dir():
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(target.parent)


def latin(style: Style) -> Path:
    """Compile the Hack UFO with the alt-hack glyphs dropped in; fontmake emits no hinting."""
    path = CACHE / f"Hack-{style.slug}.ttf"
    if path.exists():
        return path
    print(f"compile {path.stem}")
    ufo = path.with_suffix(".ufo")
    shutil.rmtree(ufo, ignore_errors=True)
    shutil.copytree(HACK_DIR / "source" / ufo.name, ufo)
    for pattern in ALTERNATES:
        for glif in (ALT_HACK_DIR / "glyphs").glob(f"{pattern}/{style.slug.lower()}/*.glif"):
            shutil.copy(glif, ufo / "glyphs" / glif.name)
    fontmake = [sys.executable, "-m", "fontmake", "-u", ufo, "-o", "ttf", "--output-dir", CACHE]
    subprocess.run([*fontmake, "--verbose", "WARNING"], check=True)
    return path


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


def set_line_metrics(font: TTFont) -> None:
    hhea = font["hhea"]
    os2 = font["OS/2"]
    hhea.ascent = LINE_ASCENT
    hhea.descent = -LINE_DESCENT
    os2.usWinAscent = LINE_ASCENT
    os2.usWinDescent = LINE_DESCENT
    os2.sTypoLineGap = LINE_ASCENT + LINE_DESCENT - os2.sTypoAscender + os2.sTypoDescender


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
    font = TTFont(latin(style))
    cjk = TTFont(cjk_upright(style.weight))
    if style.italic:
        skew_glyphs(cjk)
    merge_cjk(font, cjk)
    set_line_metrics(font)
    rename(font, style, cjk["name"].getDebugName(0))
    font["OS/2"].fsType = 0
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT / f"{style.postscript_name}.ttf"
    font.save(output)
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
