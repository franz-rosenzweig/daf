# The folio, round 2: notes

- **Best: v4, the turn as the hero.** The leaf's whole fore-edge is turning over, led by its bottom corner, the way you turn a page in a Hebrew book. It answers round 1's weakness best: there's no sheet with a dog-ear left to mistake for a document icon, just one gesture of turning. At 16 px it still reads as a light wedge with a dark band across it.
- **Runner-up: v1.** It's round 1's v2 made louder: a bigger, deeper leaf and a bolder turn. It has the most presence in the Dock and is the safest choice, but it's still a page-curl.
- **v2:** the Gemara layout sits on the face at 8 to 15% sepia, so the turn leads. It disappears below 64 px. At 1024 the blocks can still read as a floor plan or a layout template.
- **v3:** daf yomi, where the turn uncovers the next leaf underneath. It tells the story best, but the stacked edges make it look like a pad of paper, or a "Documents" stack at 32 px.
- **v5:** Moshe-flat, with no gradient or shadow. It's clean and sits closest to the camel, but it's the quietest of the six. I tried Daf's blue on the turn and dropped it: it read as a highlighter mark.
- **v6:** the wildcard. Only the corner shows, and the leaf runs off the tile. It has the strongest presence at 16 px, but it breaks the 60 to 68% fill rule, and it can read as the tile itself peeling like a sticker.
- **Weak in v4, honestly:** the face shrinks to a slanted wedge, so it's less obviously a leaf, and some will see a folded napkin or a paper cone. It also carries the largest gradient area of the set (still only on the turn). Next to Moshe's yellow, all six are paler and quieter.
- Run `python3 make.py [vN]` to regenerate everything. Each variation is a parameter set in `VARIANTS`.
