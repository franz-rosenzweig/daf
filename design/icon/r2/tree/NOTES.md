# Round 2: a book growing a tree

- **Best: V6, "the leaf is the tree"** (`v6.svg`, `best-1024.png`). Round 1's dry beech leaf stands upright as a whole tree. Its midrib is the trunk and its veins are the branches. Its tip is dog-eared like a page, and its stalk is rooted in a closed book, with one root over the front edge. It's one bold shape that reads at 32 and even 16 px as a tree on a book. It's the most specific of the six because the leaf is the page, which is the meaning of daf. `v6-small.svg` is a separate drawing for 32 px and below: no veins, a heavier trunk and a thicker book.
- **The cliché risk:** an open book with a tree or sapling growing out of it is the stock logo for education, libraries and ed-tech. V1, V3 and V4 sit right inside it; the crafted leaf and lines of text soften the problem but don't solve it. V2 (a tree on a stack of books) is a common library motif too. V5 and V6 stay clear of the open book, and V6 is the furthest from the cliché.
- **V5, bonsai:** a leaning trunk in a closed book used as its tray, carrying beech sprays. It has the most character and fits "an hour a day, compounding" best, since a bonsai is daily care over years. It's wide and busy, though, and below 64 px it reads as a twig on a plank.
- **V2:** a tree on two closed books whose leaves carry lines of text. It reads well at small sizes, but the crown is fussy and the motif is familiar.
- **Honest weaknesses of V6:**
  - The vein-branches are a chevron pattern and can read as a fishbone.
  - A tree made of one leaf can come across as a generic eco or green-publishing mark.
  - The book is drawn square from the front, so it's only a slab with a rounded spine. It reads as a book mainly through its page lines, and those disappear below 32 px.
  - The parchment on a white tile is low-contrast next to Moshe's saturated camel.
- **Technique, same as round 1:** feTurbulence grain, one feSpecularLighting edge lit from above, and one soft ground shadow, all drawn in cubic Béziers. `make.py` measures each object and scales it to 64% of the tile. It also stretches kit's paint wait at runtime, without editing kit.py, so the seven-row sheet has time to render.
- **To regenerate:** `python3 make.py [vN]`.
