# Malo

Malo is a personal monospace font. Latin glyphs come from Menlo, the monospace font bundled with macOS, and CJK glyphs come from [WenYuan Sans SC](https://github.com/takushun-wu/WenYuanFonts). Each CJK glyph fills exactly two Latin cells, so mixed text and Markdown tables stay aligned.

## Build

```sh
uv sync
uv run build.py            # all four styles into fonts/
uv run build.py --style Regular
uv run build.py --clean    # rebuild cached intermediates under build/
```

The first run copies `Menlo.ttc` from `/System/Library/Fonts/` and downloads WenYuan into `sources/upstream/`. Open `specimen.html` in a browser to preview the result.

## How the build works

1. Subset the WenYuan variable font to the CJK ranges and drop the layout tables.
2. Instantiate Regular (400) and Bold (700). Scale each instance to the 2048 upem of Menlo, decompose composites, centre each glyph in a 2466-unit double cell, and remove overlaps. Cache the result per weight.
3. For italic styles, shear the CJK glyphs by 11 degrees around half the cap height to match Menlo Italic.
4. Thicken the Menlo Regular and Italic outlines to weight 420, in proportion to the stem difference between Menlo Regular and Bold, while the baseline, x-height and cap height stay in place; the CJK glyphs and the declared weight stay at 400. Append the glyphs and cmap entries that Menlo lacks to the matching Menlo face, set the line height to 1.4 em, strip all TrueType hinting, and rename the family to Malo.

To adjust CJK placement or line height, change `CJK_SCALE`, `ITALIC_ANGLE` and `LINE_HEIGHT` in `build.py`. To change the Latin weight, edit `latin_weight` in `STYLES`.

## Licenses

Menlo is an Apple font licensed with macOS and is not redistributable on its own. WenYuan Sans uses the SIL Open Font License 1.1 with reserved font names, so this build uses a different family name.
