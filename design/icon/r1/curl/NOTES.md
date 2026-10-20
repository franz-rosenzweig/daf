# The curl: notes

- **Best: v1.** It's a wide sheet leaning right with a soft S in its body. The top rolls back into a rounded lip, and the foot curls forward to show its darker underside. It reads as paper (not a ribbon) because the sheet is wide, and it still reads as a curled sheet at 32 px.
- **How it's built:** the sheet's side profile is drawn as Bézier arcs, turned in 3D and then swept across the width, the way a broad-nib pen makes a stroke. Where the paper turns over, it changes to the underside tint. It's flat: two parchment tones (`#DEC189` and `#BC8E52`), with no gradients, outlines, spirals or end caps.
- **v2** is the narrow, steep "single stroke" version. It's the most elegant at 256 px, but it's the least page-like, and at small sizes it starts to look like a slanted bar.
- **v3** is v1 mirrored, with three quiet text lines set right to left. It reads most as a document, but it tips toward "diploma", and the lines are mush below 64 px.
- **Weak:** the top curl is the quieter half. Below about 48 px it disappears, and what's left is a tan slab with a dark foot. At 16 px that could pass for a slice of toast.
- **Risk:** the top curl's open end shows a small dark half-moon. It's the inside of the curl, not a spiral, but a client who has twice rejected roll ends may see one.
- **Honestly:** this is the familiar "scroll" idea done cleanly, not a new mark. Parchment on a white tile also stands out less in the Dock than Moshe's white camel on yellow.
