# Malo

Malo is a personal monospace font. Latin glyphs come from [Hack](https://github.com/source-foundry/Hack) with the [alt-hack](https://github.com/source-foundry/alt-hack) slashed zero and slab `i` family, and CJK glyphs come from [WenYuan Sans SC](https://github.com/takushun-wu/WenYuanFonts). Each CJK glyph fills exactly two Latin cells, so mixed text and Markdown tables stay aligned. Nothing is hinted.

## Build

```sh
uv sync
uv run build.py            # all four styles into fonts/
uv run build.py --style Regular
uv run build.py --clean    # rebuild cached intermediates under build/
```

The first run downloads the Hack and alt-hack sources and the WenYuan font into `sources/upstream/`. Open `specimen.html` in a browser to preview the result.

## How the build works

1. Copy each Hack UFO, drop in the alt-hack glyphs (`u0030-forwardslash` for the zero, `*-slab` so `i` and its accented forms get the flat DejaVu/Menlo foot), and compile with fontmake. Cache the result per style.
2. Subset the WenYuan variable font to the CJK ranges and drop the layout tables.
3. Instantiate Regular (400) and Bold (700). Scale each instance to the 2048 upem of Hack, decompose composites, centre each glyph in a 2466-unit double cell, and remove overlaps. Cache the result per weight.
4. For italic styles, shear the CJK glyphs by 11 degrees around half the cap height to match Hack Italic.
5. Append the glyphs and cmap entries that Hack lacks to the compiled Hack file, set the line metrics to those of Meslo LG S (2584 units per line), and rename the family to Malo.

To adjust CJK placement, change `CJK_SCALE` and `ITALIC_ANGLE` in `build.py`.

## Licenses

Hack uses the MIT License plus the Bitstream Vera License. WenYuan Sans uses the SIL Open Font License 1.1 with reserved font names, so this build uses a different family name.
