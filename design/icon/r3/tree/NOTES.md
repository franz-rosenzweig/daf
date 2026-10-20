# Round 3: refining V2, the beech tree rooted in two closed books ("Tree D")

## What changed, and why

Each move is shown alone against V2 on `sheet.png`.

1. **V2,** unchanged, for reference.
2. **Crown:** ten leaves became five larger ones. They grow in an oval on short branches that alternate up the leader, and the top leaf keeps its dog-ear and lines of text. I tried a tight five-leaf fan first, but it read as a lotus. Six and seven leaves brought the fussiness back.
3. **Placement:** the object is lowered by 28 px, so the centre of its box sits at y 506, just above the tile's middle (V2's was at 478). It fills 64% of the tile's height.
4. **Books:** the lower book now faces us spine-on, in a deeper brown, with a pair of raised bands near each end and the edges of its boards. The upper book is offset to the right and shows its pages and the rounded end of its spine. There's no lettering anywhere.
5. **Presence:** the parchment is a step deeper and the trunk is 25% heavier and darker. There's no gradient wash.
6. **Accent:**
   - **6a** puts Daf's blue (#1A7DA4) on the upper book's spine end, like a quarter-bound book.
   - **6b** puts the deep red-brown (#7A3B1E) in the same place. Against the brown books it nearly disappears.
   - Painting the whole lower spine in either colour was too loud, so neither is on the sheet.
7. **Final** (`final.svg`) combines moves 2 to 5 with the blue spine end.

## Recommendation

Use `final.svg` for 64 px and up, and `final-small.svg` for 16 to 48 px.

The small drawing turns the crown into one soft, five-lobed silhouette in a single tone, with a heavier trunk and the books as two clean slabs. It keeps the blue spine end. A small crown of separate leaves broke into a maple-leaf outline at 32 to 48 px, which is why it changed. `small.png` shows both drawings at 16, 24, 32 and 48 px, on light and dark, at true size and magnified four times.

## Honest weaknesses

- **Small sizes:** below 48 px the large drawing's crown turns to noise, so the switch to the small drawing is needed.
- **The small crown:** it's generic. It reads as "a tree", not as a beech.
- **The blue accent:** the lit edge lightens the top of the blue end slightly toward teal.
- **The lower book:** spine-on and spine-deep, it's the heaviest shape in the icon and could pass for a plain wooden plank.
- **Next to Moshe:** the icon is still quieter than the camel, because it's parchment on white beside his saturated yellow tile.
- **The cliché:** a tree on a stack of books remains a known library motif. The crafted leaves and the dog-ear make it Daf's own, but they don't make it unique.

## Regenerating

Run `python3 make.py`. It also writes `final-1024.png`. The script stretches kit's paint wait at runtime, without editing kit.py, so the eight-row sheet has time to render.
