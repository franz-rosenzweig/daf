"""Round 1 at a glance: each concept's best drawing at 256, at 64/32/16 on light and dark,
and in a Dock beside Moshe."""
import base64, sys
sys.path.insert(0, "/srv/dev/daf/design/icon"); import kit

ROWS = [
    ("curl/v1.svg", "1. The curl", "Your first idea, flat like the camel: the top rolls back, the foot curls forward. No rods, no spirals.", "Below about 48 px the top curl fades and it’s a tan slab with a dark foot."),
    ("folio/v2.svg", "2. The folio", "One leaf, its corner turned the way a Hebrew page turns, showing the darker back.", "Closest to Apple’s polish, but also closest to the generic document icon."),
    ("leaf/v2.svg", "3. The leaf", "A dry beech leaf whose tip folds down like a dog-ear; the midrib is the gutter.", "The prettiest and most its own, but under 32 px it’s just a leaf: plant-app risk."),
    ("vilna/v1.svg", "4. The Vilna page", "The daf itself: main text, Rashi and Tosafot as four blocks on a leaf.", "At 16 px it’s a page with a brown middle; to others it may read as a layout template."),
    ("ring/v1.svg", "5. The hour ring", "Pages fanned into a full circle, two-thirds deeper like the ring on Today.", "Reads as a citrus slice or a fitness ring. I’d drop it."),
]
MOSHE = "/srv/dev/moshe-next/frontend/public/icons/icon.svg"
u = lambda p: "data:image/svg+xml;base64," + base64.b64encode(open(p, "rb").read()).decode()
moshe = u(MOSHE)
rows = []
for path, name, idea, weak in ROWS:
    s = u("/srv/dev/daf/design/icon/r1/" + path)
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
