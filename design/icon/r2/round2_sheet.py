"""Round 1 at a glance: each concept's best drawing at 256, at 64/32/16 on light and dark,
and in a Dock beside Moshe."""
import base64, sys
sys.path.insert(0, "/srv/dev/daf/design/icon"); import kit

ROWS = [
    ("vilna/v2.svg", "Vilna A. The daf, its corner turned", "The Gemara page with its bottom-left corner lifting the Hebrew way, showing the darker back. Both designers ended up here from opposite sides.", "Blockier than round 1 at large sizes: the tilt and arch were traded for a crisp 32 px."),
    ("vilna/v4.svg", "Vilna B. Real type colour", "Heavy main-text lines inside fine commentary lines; under 64 px it becomes the solid blocks.", "To someone who doesn’t know the daf, the lines can read as a generic text-document icon."),
    ("vilna/v5.svg", "Vilna C. One blue word", "The solid page with the opening word in Daf’s blue, like Moshe’s eye dot.", "A fourth colour; at a glance it can read as a stamp."),
    ("vilna/v3.svg", "Vilna D. The open Gemara", "Two amudim across the gutter, the Rashi columns meeting in the middle.", "The smallest of the set; at 16 px it’s two brown smudges."),
    ("vilna/v6.svg", "Vilna E. No leaf, just the layout", "The tile is the paper, so the layout can be a third bigger. The boldest at 16 px.", "Loses the old-paper feeling; one block can look like an armchair."),
    ("folio/v4.svg", "Folio A. The turn is the icon", "The whole fore-edge turning over, led by the bottom corner, as in a Hebrew book.", "The face becomes a wedge: some will see a folded napkin or a paper cone."),
    ("folio/v2.svg", "Folio B. A daf on the face", "The round 1 leaf with the Gemara layout whispered in pale sepia; the turn leads.", "The layout vanishes below 64 px; at 1024 it can look like a floor plan."),
    ("folio/v1.svg", "Folio C. Round 1, louder", "A bigger, deeper leaf and a bolder turn: the most Dock presence.", "Still a page curl, the safest and least particular."),
    ("folio/v3.svg", "Folio D. Daf yomi", "The top leaf turning to uncover the next one underneath: a page a day.", "The stacked edges can read as a notepad at 32 px."),
    ("tree/v6.svg", "Tree A. The leaf is the tree", "Round 1’s dog-eared beech leaf standing as a whole tree, rooted in a closed book: the leaf is the page, which is what daf means.", "The veins can read as a fishbone, and a one-leaf tree can pass for an eco logo."),
    ("tree/v5.svg", "Tree B. Bonsai on a book", "A leaning trunk whose roots grip a closed book, its tray: daily care over years, an hour a day compounding.", "Wide and busy; under 64 px it’s a twig on a plank."),
    ("tree/v3.svg", "Tree C. One leaf sprouting", "The dog-eared leaf on a curved stem rising from an open book’s gutter.", "Open book plus a plant is the stock school-and-library logo."),
    ("tree/v2.svg", "Tree D. A tree on two books", "A beech tree rooted in two closed books, its leaves carrying lines of text.", "Reads well small, but the crown is fussy and the idea is familiar."),
]
MOSHE = "/srv/dev/moshe-next/frontend/public/icons/icon.svg"
if len(sys.argv) > 2:
    ROWS = [r for r in ROWS if r[0].startswith(sys.argv[2] + "/")]
u = lambda p: "data:image/svg+xml;base64," + base64.b64encode(open(p, "rb").read()).decode()
moshe = u(MOSHE)
rows = []
for path, name, idea, weak in ROWS:
    s = u("/srv/dev/daf/design/icon/r2/" + path)
    small = "".join(f'<img src="{s}" width="{n}" height="{n}">' for n in (64, 32, 16))
    rows.append(f'<div class="r"><div class="big"><img src="{s}" width="230" height="230"></div>'
                f'<div class="col"><div class="st lt">{small}</div><div class="st dk">{small}</div>'
                f'<div class="dock"><img src="{moshe}" width="58" height="58"><img src="{s}" width="58" height="58"></div></div>'
                f'<div class="lb"><b>{name}</b><p>{idea}</p><p class="w">{weak}</p></div></div>')
html = ('<html><head><meta charset="utf-8"></head><body style="margin:0;background:#fff;font:15px -apple-system,Helvetica,Arial,sans-serif;color:#222">'
        '<style>.r{display:flex;align-items:center;gap:22px;padding:16px 26px;border-bottom:1px solid #eee}'
        '.big{background:#ececec;border-radius:18px;padding:6px}.col{display:flex;flex-direction:column;gap:8px}'
        '.st{display:flex;gap:16px;align-items:center;padding:10px 16px;border-radius:12px}.lt{background:#f3f3f3}.dk{background:#1e1e1e}'
        '.dock{display:flex;gap:10px;padding:8px 14px;border-radius:18px;background:linear-gradient(#d9d6d2,#c9c6c2);width:max-content}'
        '.lb{max-width:340px}.lb b{font-size:19px;display:block;margin-bottom:4px}.lb p{margin:4px 0;color:#444;line-height:1.35}.lb .w{color:#8a5a2b}</style>'
        + "".join(rows) + '</body></html>')
p = kit._Page(1060, 292 * len(ROWS) + 10)
try:
    p.shoot(html, sys.argv[1])
finally:
    p.close()
print(sys.argv[1])
