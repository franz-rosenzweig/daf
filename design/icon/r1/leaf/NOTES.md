# Concept 6: the leaf that is a page

- **Best: V2** (`v2.svg`, `best-1024.png`). It's a dry beech leaf on the diagonal with its tip turned down like a dog-eared page corner. The turned-down tip shows the leaf's paler underside, so the fold looks natural and also reads as paper. The lit upper half and shaded lower half make the midrib look like a gutter, and the lower half's veins run almost square to it, like lines of text. It fills 58% × 66% of the tile, and the blade's centroid sits at (518, 490).
- **V1** (upright beech, two pages, veins as lines of text, no fold) is the quiet control. Without the fold it reads as a generic leaf, and upright it starts to look like a spade or a bodhi leaf.
- **V3** (tilted elm, lines of text, tip folded flat) reads most like a page. But the flat top makes the blade look cut off, a little like a shield, and the leaf gets lost.
- **Honest weakness:** from 16 to 32 px every version is just a tan leaf. The fold and the lines only show from about 64 px up, so at small sizes it can still pass for a plant or nature app.
- **Next to Moshe:** the camel is a flat, saturated silhouette. The leaf is pale parchment on white, with grain, a lit edge and a folded flap as a second layer, so in the Dock it will look quieter and more rendered than the camel.
- **Technique:** paper grain from feTurbulence (fine grain plus slow mottling), clipped to the leaf. One feSpecularLighting edge lit from above at low strength, and one warm contact shadow. The whole leaf is cubic Béziers, and the slight wave in the margin is a Catmull-Rom fit.
- **To regenerate:** `python3 make.py [v1|v2|v3]`. Every geometry, colour and fold setting is a parameter at the bottom of the file.
