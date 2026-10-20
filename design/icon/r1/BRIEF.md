# Daf icon, round 1: the brief

## The brief in five lines

1. **The one idea:** show up for the page every day. An hour of reading a day, and what you
   read comes back to you. Daf is the Hebrew word for a leaf of a book, as in *daf yomi*,
   a page of Talmud a day.
2. **Audience:** one reader, Nathan. He'll see it every day in his Mac's Dock beside Moshe
   (the camel) and Dvarim, and on his phone's first screen beside Instagram and Reddit.
3. **Feeling:** calm, old paper, quietly made. Natural rather than glossy; a reading room,
   not a gadget.
4. **Constraints:** a white tile, a parchment-coloured motif, and no green.
   - Flat or nearly flat. Moshe's camel is the bar: one white silhouette on a coloured tile,
     with a lighter tint for the far legs and a single dot for the eye.
   - No letters or words, Hebrew included.
   - **No spirals or swirls.** He has asked twice.
   - No generic open book, no glasses, no bookmark glyph.
5. **Sizes:** macOS 16 to 1024. Android 48 to 512, plus a maskable version. Web favicon 16
   and 32, and apple-touch 180.

## Colours

Taken from Daf's own sepia theme (`web/style.css`) and from parchment.

- **Tile:** `#FFFFFF` to `#F2EFEA`, from `kit.tile`.
- **Parchment:** light `#EAD7B0`, mid `#D9BA80`, deep `#BC8E52`.
- **Ink:** sepia `#9A5B1F`, deep `#7A4614`, darkest `#3A3127`.
- **Optional accent:** Daf's blue, `#1A7DA4` in the light theme and `#57B3D7` in the dark.

## Principles we judge by

1. **One object** with a strong silhouette that still reads at 16 px.
2. **One light, from above.** Depth comes from at most a few layers.
3. **At most three tones on the object,** plus grain or lighting if your technique calls for it.
4. **The object comes from Daf's world** (the leaf, the Gemara page, parchment, the daily
   hour), not from the "reading app" category.
5. **Size and position:**
   - The object fills about 60 to 68% of the tile's height or width.
   - It sits on the tile's visual centre, which is a little above the geometric one.
6. **No unintended readings:** no shapes that look like letters, numbers or other symbols.
7. **The Dock test:** it must look at home next to Moshe's camel
   (`/srv/dev/moshe-next/frontend/public/icons/icon-512.png`, with its SVG beside it).

## Twelve concepts

1. **The folio:** one leaf with its corner turned up, showing the back (*amud bet*).
   - The idea: a daf has two sides; you turn the page every day.
   - **Risk:** the generic "document" icon (Pages, Files).
2. **The Vilna page:** the shape of a Gemara page in solid blocks, with the main text in the
   middle and the commentary wrapped around it.
   - The idea: the daf itself, the most recognisable page there is.
   - **Risk:** it turns to noise at 16 px.
3. **The curl:** one sheet whose top curls back and whose bottom curls forward, as a single
   flat silhouette.
   - The idea: Nathan's first idea for the icon.
   - **Risk:** it reads as a ribbon, a wave, or a diploma.
4. **The ribbon:** a silk marker ribbon lying across a page edge.
   - The idea: where you stopped yesterday, and where you begin today.
   - **Risk:** the generic bookmark glyph.
5. **The hour ring:** leaves of paper fanned into a full circle.
   - The idea: the hour a day, the ring Daf shows on Today.
   - **Risk:** it reads as a flower, a camera aperture, or a fitness ring.
6. **The leaf that is a page:** a tree leaf in parchment, its midrib the book's gutter.
   - The idea: a book's "leaf", which is what daf means.
   - **Risk:** it reads as a plant or ecology app.
7. **The shtender:** the reading stand of the beit midrash, with a page on it.
   - **Risk:** it reads as a podium or a pulpit, and it says "religious app".
8. **The page by lamplight:** a page in a warm pool of light.
   - The idea: evening reading, the nudge at 21:00.
   - **Risk:** it reads as a sleep app.
9. **The paper hourglass.** **Risk:** cliché, and it reads as a timer app.
10. **The highlight stroke:** one marker stroke across a line.
    - **Risk:** cliché, and it reads as a notes or marker app.
11. **The candle.** **Risk:** it reads as a Shabbat or Chanukah app.
12. **The nightstand stack.** **Risk:** cliché, and it reads as a generic library app.

**Drawn in round 1:** 1 to 6. Each gets its own rendering technique, and each builder makes
three variations.
