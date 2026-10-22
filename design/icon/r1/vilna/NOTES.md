# The Vilna page: notes

- **Best: V1** (`v1.svg`, `best-1024.png`). A folio-shaped parchment leaf, tilted 3 degrees with a slight arch, holds four flat blocks. The main text sits in deep sepia, with its opening word set apart at the top right. Tosafot runs straight down the outer side, and Rashi runs down the gutter side and turns under the main text. It is 67% of the tile's height, centred at y = 498.
- **Why V1:** it has the fewest shapes and the strongest contrast at 32 and 64 px. The tilt and arch make it a leaf you could pick up rather than a wireframe, and the asymmetric wrap avoids the "pair of doors" look of a centred split.
- **V2** (upright, both commentaries wrap under, margin notes) is the most literal daf. At 32 px its two bottom blocks still read as wardrobe doors.
- **V3** (amud bet, opening word in Daf's blue) has a nice single accent, like Moshe's eye. But the blue is a fourth tone, and it can read as a stamp.
- **Weak, honestly:** at 16 px every version is a tan page with a brown core. It reads as "a page", not as "that page".
- **Weak, honestly:** without lines of text, someone who doesn't know the daf may read the blocks as a layout template or a floor plan (a Pages or InDesign kind of icon). The wrap of commentary around the main text is the only Talmud cue.
- **Next to Moshe** it is quieter, with less presence: a pale page on a white tile against the camel's single bold silhouette.
- Everything is set by the parameters in `make.py` (`vilna()` for the layout, `cfg()` for the tones, tilt and curve). Run `python3 make.py` to regenerate the SVGs, `sheet.png` and `best-1024.png`.
