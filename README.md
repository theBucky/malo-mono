# malo

malo is a monospace font for mixed chinese and english text. latin glyphs come from menlo, the monospace font that ships with macos. cjk glyphs come from [wenyuan sans sc](https://github.com/takushun-wu/WenYuanFonts). every cjk glyph is exactly two latin cells wide, so code and markdown tables stay aligned.

variants swap the latin glyphs:

- malokeley: [berkeley mono](https://usgraphics.com/products/berkeley-mono)
- maloist: [goeist mono](https://github.com/shadcn-labs/goeist-font), a rounded geist mono
- malople: [maple mono](https://github.com/subframe7536/maple-font) nl, the cut without ligatures
- maloha: [hack](https://github.com/source-foundry/Hack), with the slashed zero and straight i from [alt-hack](https://github.com/source-foundry/alt-hack)

## build

```sh
uv sync
uv run build.py                                # clear build/, then every font and style into fonts/
uv run build.py --family Maloist               # one font, reusing the cache
uv run build.py --family Malo --style Regular  # filters repeat and combine
uv run build.py --style Bold --clean           # clear build/ first
```

the build only reads these latin fonts from `sources/upstream/`, so place them there first:

- malo: `Menlo.ttc`, copied from `/System/Library/Fonts/`
- malokeley: the four berkeley mono files (`BerkeleyMono-Regular.ttf`, `-Oblique`, `-Bold`, `-Bold-Oblique`)
- malople: the two maple mono nl variable fonts (`MapleMonoNL[wght].ttf`, `MapleMonoNL-Italic[wght].ttf`)

wenyuan, goeist mono and hack are downloaded from their latest github releases into `build/`, beside the intermediate fonts, so clearing `build/` also updates them. the alt-hack glyphs come from a pinned commit. open `specimen.html` in a browser to see every font.

## how the build works

1. cut wenyuan down to its full-width glyphs in the cjk ranges.
2. make a regular (400) and a bold (700) copy. scale the glyphs to 94% of the latin em, put each one in a double cell, and line up the middle of the cjk em box with the middle of the latin capitals. the result is cached in `build/`.
3. for italics, slant the cjk glyphs to the latin italic angle.
4. add the cjk glyphs to the latin font, set the line height to 1.3 em around the same middle, make the underline 0.1 em thick, and rename the font. ghostty draws box drawing itself as thick as the underline, so every font gets the same box lines as berkeley mono.

latin glyphs stay as they ship, apart from the changes below. menlo bold has no box drawing, so malo bold takes those glyphs from menlo regular, the same ones menlo italic uses. goeist mono ships coding ligatures, which draw several characters in one cell, so maloist drops them. maple mono ships as variable fonts, so malople pins the weight at 400 and 700. maloha swaps in the slashed zero and the straight i, with its accented forms, from alt-hack. the em size, cell width, the capital middle and the italic angle all come from the latin font. to change cjk size or line height, edit `CJK_SCALE` or `LINE_HEIGHT` in `build.py` and rebuild with `--clean`.

## licenses

menlo comes with macos and can't be shared alone. berkeley mono is a commercial font from u.s. graphics and can't be shared either. goeist mono and maple mono use the sil open font license 1.1 without reserved font names. hack and alt-hack use the mit license, and the bitstream vera glyphs under hack use the bitstream vera license, which reserves the names bitstream and vera. wenyuan sans uses the sil open font license 1.1 with reserved font names, which is why this font uses a different name.
