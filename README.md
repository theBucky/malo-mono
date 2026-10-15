# Malo

Malo is a personal monospace font family. Latin glyphs come from Menlo, the monospace font bundled with macOS, and CJK glyphs come from [WenYuan Sans SC](https://github.com/takushun-wu/WenYuanFonts). Each CJK glyph fills exactly two Latin cells, so mixed text and Markdown tables stay aligned.

## Build

```sh
uv sync
uv run build.py            # all four styles, into fonts/
uv run build.py --style Regular
uv run build.py --clean    # rebuild cached intermediates under build/
```

The first run copies `Menlo.ttc` from `/System/Library/Fonts/` and downloads WenYuan into `sources/upstream/`. Open `specimen.html` in a browser to preview the result.

## How the build works

1. Subset the WenYuan variable font to the CJK ranges and drop the layout tables.
2. Instantiate Regular (400) and Bold (700). Scale each instance to the Menlo upem at 92%, centre each glyph in a double cell, with the ink box of 国 centred on the midline of the Latin capitals, and remove overlaps. Cache the result per weight.
3. For italic styles, shear the CJK glyphs around the same midline to the Menlo italic angle.
4. Map every CJK codepoint to the WenYuan glyph, over any half-width glyph Menlo had, set the line height to 1.4 em centred on the same midline, strip all TrueType hinting, and rename the family. Menlo outlines and weights stay as they ship.

Upem, cell width, the capital midline and italic angle come from Menlo. To adjust CJK size or line height, change `CJK_SCALE` or `LINE_HEIGHT` in `build.py`, then rebuild with `--clean`.

## Licenses

Menlo is an Apple font licensed with macOS and is not redistributable on its own. WenYuan Sans uses the SIL Open Font License 1.1 with reserved font names, so this build uses a different family name.
