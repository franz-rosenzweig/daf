"""Round 1 at a glance: each concept's best drawing at 256, at 64/32/16 on light and dark,
and in a Dock beside Moshe."""
import base64, sys
sys.path.insert(0, "/srv/dev/daf/design/icon"); import kit

ROWS = [
    ("tree/v2.svg", "1. Tree D as you picked it", "Round 2’s drawing, unchanged.", "The crown is busy; it sits a little high."),
    ("tree/crown.svg", "2. A calmer crown", "Five larger beech leaves in one oval, the top one still dog-eared with lines of text.", "Fewer leaves: less of a canopy, more of a sapling."),
    ("tree/place.svg", "3. Moved onto the visual centre", "Lowered 28 px so the weight sits in the middle; 64% of the tile’s height.", "On its own it’s a subtle change."),
    ("tree/books.svg", "4. Books with character", "The lower book spine-on in a deeper brown with raised bands; the upper offset, pages showing.", "The dark lower book is the heaviest shape and can look like a plank."),
    ("tree/presence.svg", "5. More Dock presence", "A step deeper parchment and a firmer trunk; no gradient wash.", "Still quieter than Moshe’s yellow."),
    ("tree/accent-blue.svg", "6. One blue spine", "The upper book’s spine end in Daf’s blue, like Moshe’s eye dot.", "The light edge pulls it a little toward teal."),
    ("tree/final.svg", "7. All of it together", "2 to 5 combined, with the blue spine end. The designer’s recommendation.", "Below 48 px only the simplified drawing reads (next sheet)."),
]
MOSHE = "/srv/dev/moshe-next/frontend/public/icons/icon.svg"
if len(sys.argv) > 2:
    ROWS = [r for r in ROWS if r[0].startswith(sys.argv[2] + "/")]
u = lambda p: "data:image/svg+xml;base64," + base64.b64encode(open(p, "rb").read()).decode()
moshe = u(MOSHE)
rows = []
for path, name, idea, weak in ROWS:
    s = u("/srv/dev/daf/design/icon/r3/" + path)
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
