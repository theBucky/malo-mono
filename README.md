# malo

malo is a monospace font for mixed chinese and english text. latin glyphs come from menlo, the monospace font that ships with macos. cjk glyphs come from [wenyuan sans sc](https://github.com/takushun-wu/WenYuanFonts). every cjk glyph is exactly two latin cells wide, so code and markdown tables stay aligned.

malo alt is the same font with latin glyphs from [berkeley mono](https://usgraphics.com/products/berkeley-mono) instead of menlo.

## build

```sh
uv sync
uv run build.py                  # malo, all four styles, into fonts/
uv run build.py --alt            # malo alt
uv run build.py --style Regular  # one style only
uv run build.py --clean          # drop the cache in build/ first
```

the first run copies `Menlo.ttc` from `/System/Library/Fonts/` and downloads wenyuan into `sources/upstream/`. `--alt` expects the four berkeley mono files (`BerkeleyMono-Regular.ttf`, `-Oblique`, `-Bold`, `-Bold-Oblique`) in the same directory. open `specimen.html` in a browser to see both fonts.

## how the build works

1. cut wenyuan down to the cjk ranges.
2. make a regular (400) and a bold (700) copy. scale the glyphs to 94% of the latin em, put each one in a double cell, and line up the middle of 国 with the middle of the latin capitals. the result is cached in `build/`.
3. for italics, slant the cjk glyphs to the latin italic angle. berkeley mono obliques use 11 degrees.
4. add the cjk glyphs to the latin font, set the line height to 1.3 em around the same middle, and rename the font.

latin glyphs stay as they ship. the em size, cell width, the capital middle and the italic angle all come from the latin font. to change cjk size or line height, edit `CJK_SCALE` or `LINE_HEIGHT` in `build.py` and rebuild with `--clean`.

## licenses

menlo comes with macos and can't be shared alone. berkeley mono is a commercial font from u.s. graphics and can't be shared either. wenyuan sans uses the sil open font license 1.1 with reserved font names, which is why this font uses a different name.
