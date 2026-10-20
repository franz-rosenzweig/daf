# Round 4: the macOS 26 appearances

## What I made

- **`dark.svg` and `dark-small.svg`:** the same drawing on a warm charcoal tile, running from #2A2622 to #1E1B18.
  - The parchment is lifted one step (leaves #EACD95 and #D7AC68, pages #F6EBD2) and has a faint warm glow, so it reads as lit paper.
  - The trunk is lifted to #93633A, because round 3's dark trunk disappeared against the charcoal.
  - The blue spine end uses Daf's dark-theme blue, #57B3D7.
  - The contact shadow is black and tighter, so it doesn't sit on the charcoal as a brown haze.
  - A faint light rim, brighter at the top, keeps the tile's edge visible on a dark desktop.
- **`tinted.svg` and `tinted-small.svg`:** one tone of grey on a dark grey tile, with no colour of its own. The values are spaced so each part stays distinct once macOS adds the user's tint:
  - pages #F0F0F0
  - leaves #D6D6D6 and #BABABA
  - trunk #8E8E8E and upper book cover #8A8A8A
  - lower book #5A5A5A
  - spine end #3A3A3A, the darkest mark, so it still works as the eye dot
- **`layers/`:** for Icon Composer, `background`, `books` and `tree` (the roots, trunk, branches and crown), as transparent 1024 PNGs and SVGs.
  - All three share one canvas and one position.
  - The background is a full square, with no tile shape and no shadow.
  - The layers keep the paper grain but have no baked shadow, lit edge or glow, because Icon Composer adds its own shadow and glass.
  - `layers/dark/` holds the same three layers in the dark palette, in case Composer needs them.
- **`light.svg` and `light-small.svg`:** round 3's shipped icons, copied unchanged for the comparison.
- **`sheet.png`:** the light, dark and tinted icons, then their small drawings, at 256/64/32/16 on light and dark. Below that is a Dock strip beside Moshe on a light desktop and a dark one. Its last icon is the tinted one coloured blue, as a rough simulation of what macOS does.

The geometry is imported from `r3/tree/make.py`, so there's one source for the drawing. `make.py` checks that the books and tree layers, put back together, redraw round 3's final exactly: the same paths and the same ids.

## Honest weaknesses

- **Canvas scale is an assumption.** I've assumed Icon Composer masks the whole 1024 canvas, so the layers are scaled by 1024/824. That makes the object fill 64% of the mask, as it does on kit's tile. If Composer turns out to use the older 824 grid, set `FULL_BLEED = 1` in `make.py` and re-run.
- **There's no Clear version.** Icon Composer derives Clear from the layers. Under its glass the baked grain and colours may look muddy, and I haven't been able to check that in Composer.
- **The tinted greys are a guess.** They're my estimate of how macOS maps luminance to tint, and the coloured Dock icon is only a simulation.
- **Dark icons fade on a dark desktop.** At 16 to 32 px the dark and tinted tiles almost disappear on a dark desktop; the rim helps from about 48 px up.
- **Two blues.** The dark icon's blue (#57B3D7) differs from the light icon's (#1A7DA4) on purpose, following Daf's own themes. If one blue everywhere matters more, change it.
- **Small sizes need the small drawings.** Below 48 px the full drawing's crown breaks up in every appearance.
- **The lower book is the weakest part in Dark.** Spine-on, it's still the dullest shape on the charcoal.

## Regenerating

Run `python3 make.py`. It reads `r3/tree/final.svg` and `final-small.svg` for their exact placement.
