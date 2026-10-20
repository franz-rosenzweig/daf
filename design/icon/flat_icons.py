import math, sys
def squircle(cx, cy, r, n=5.0, steps=360):
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        pts.append(f"{cx + r * math.copysign(abs(c) ** (2 / n), c):.1f},{cy + r * math.copysign(abs(s) ** (2 / n), s):.1f}")
    return "M" + " L".join(pts) + " Z"
SQ = squircle(512, 512, 412)
def tile(bg_top, bg_bot, inner, shadow=0.28):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
<defs><filter id="sh" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="14" stdDeviation="16" flood-color="#000" flood-opacity="{shadow}"/></filter>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{bg_top}"/><stop offset="1" stop-color="{bg_bot}"/></linearGradient>
<clipPath id="cl"><path d="{SQ}"/></clipPath></defs>
<g filter="url(#sh)"><path d="{SQ}" fill="url(#bg)"/></g><g clip-path="url(#cl)">{inner}</g></svg>'''
# A scroll as one flat silhouette: the page between two rolls, the rolls a little wider, tilted right.
# Two hairline gaps say where page meets roll; nothing else.
def scroll(fill, gap):
    return f'''<g transform="translate(512 512) rotate(12)">
  <path d="M-150 -196 C-160 -70 -140 70 -154 196 L154 196 C140 70 160 -70 150 -196 Z" fill="{fill}"/>
  <rect x="-196" y="-262" width="392" height="66" rx="33" fill="{fill}"/>
  <rect x="-196" y="196" width="392" height="66" rx="33" fill="{fill}"/>
  <path d="M-150 -192 L150 -192 M-154 192 L154 192" stroke="{gap}" stroke-width="10" stroke-linecap="round"/>
</g>'''
# A Gemara page: the main text in a column in the middle, its first word set large, commentary
# down both sides and across the foot. Lines only, one ink.
def gemara(ink, line_main=16, line_side=9):
    g = []
    # first word box
    g.append(f'<rect x="-62" y="-250" width="124" height="54" rx="10" fill="{ink}"/>')
    # main column lines
    y = -170
    for k in range(9):
        w = 150 if k not in (8,) else 90
        g.append(f'<line x1="-{w}" y1="{y}" x2="{w}" y2="{y}" stroke="{ink}" stroke-width="{line_main}" stroke-linecap="round"/>')
        y += 38
    # side commentary columns (Rashi and Tosafot)
    y = -250
    while y <= 150:
        g.append(f'<line x1="-268" y1="{y}" x2="-190" y2="{y}" stroke="{ink}" stroke-width="{line_side}" stroke-linecap="round"/>')
        g.append(f'<line x1="190" y1="{y}" x2="268" y2="{y}" stroke="{ink}" stroke-width="{line_side}" stroke-linecap="round"/>')
        y += 22
    # across the foot
    y = 180
    for k in range(4):
        w = 268 if k < 3 else 160
        g.append(f'<line x1="-{w}" y1="{y}" x2="{w if k < 3 else 60}" y2="{y}" stroke="{ink}" stroke-width="{line_side}" stroke-linecap="round"/>')
        y += 22
    return '<g transform="translate(512 500)">' + "".join(g) + '</g>'
variants = {
  "a": tile("#FFFFFF", "#EEEAE2", scroll("#D4AE6E", "#FFFFFF")),
  "b": tile("#F5E3BA", "#DDB676", scroll("#FFFFFF", "#E6C68C")),
  "c": tile("#F6E9CC", "#E4CC9B", gemara("#6E4F2C")),
  "d": tile("#FFFFFF", "#EEEAE2", '<g transform="translate(512 512) scale(1.0)"><rect x="-300" y="-300" width="600" height="600" rx="40" fill="#F1E2C2"/></g>'.replace('<rect', '<rect') + gemara("#8A6438")),
}
for k, v in variants.items():
    open(f"{k}.svg", "w").write(v)
print("ok")
