# Malo

Malo is a personal monospace font family in two flavours. Latin glyphs come from Menlo, the monospace font bundled with macOS, in **Malo**, and from [Geist Mono](https://github.com/vercel/geist-font) in **Malo V2**. CJK glyphs come from [WenYuan Sans SC](https://github.com/takushun-wu/WenYuanFonts) in both. Each CJK glyph fills exactly two Latin cells, so mixed text and Markdown tables stay aligned.

## Build

```sh
uv sync
uv run build.py            # both families, all four styles, into fonts/
uv run build.py --family "Malo V2" --style Regular
uv run build.py --clean    # rebuild cached intermediates under build/
```

The first run copies `Menlo.ttc` from `/System/Library/Fonts/` and downloads WenYuan and the Geist release into `sources/upstream/`. Open `specimen.html` in a browser to preview the result and switch between the two families.

## How the build works

1. Subset the WenYuan variable font to the CJK ranges and drop the layout tables.
2. Instantiate Regular (400) and Bold (700). Scale each instance to the upem of the Latin font, decompose composites, centre each glyph in a double cell, with the ink box of 国 centred on half the Latin cap height, and remove overlaps. Cache the result per family and weight.
3. For italic styles, shear the CJK glyphs around half the cap height to the Latin italic angle.
4. Render the Latin Regular and Italic faces at weight 420 while the declared weight stays at 400. Menlo has no variable axis, so its outlines are thickened in proportion to the stem difference between Menlo Regular and Bold while the baseline, x-height and cap height stay in place. Geist Mono is instantiated from its variable fonts.
5. Map every CJK codepoint to the WenYuan glyph, over any half-width glyph the Latin font had, take the line height from WenYuan, strip all TrueType hinting, and rename the family.

Upem, cell width, cap height and italic angle come from the Latin font. To adjust CJK size, change `CJK_SCALE` in `build.py`. To change the Latin weight, edit `latin_weight` in `STYLES`.

## Licenses

Menlo is an Apple font licensed with macOS and is not redistributable on its own. Geist Mono and WenYuan Sans use the SIL Open Font License 1.1 with reserved font names, so this build uses a different family name.
