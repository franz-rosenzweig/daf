import math, sys
def squircle(cx, cy, r, n=5.0, steps=360):
    pts = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        pts.append(f"{cx + r * math.copysign(abs(c) ** (2 / n), c):.1f},{cy + r * math.copysign(abs(s) ** (2 / n), s):.1f}")
    return "M" + " L".join(pts) + " Z"
def spiral(cx, cy, r, turns=2.6, flip=1):
    # an Archimedean spiral from the rim inward: the rolled layers of paper seen end-on
    pts, n = [], 120
    for i in range(n + 1):
        t = i / n
        a = flip * (t * turns * 2 * math.pi) + (math.pi if flip < 0 else 0)
        rr = r * (1 - t * 0.86)
        pts.append(f"{cx + rr * math.cos(a):.1f},{cy + rr * math.sin(a):.1f}")
    return "M" + " L".join(pts)
sq = squircle(512, 512, 412)
P = dict(paper0="#E3EECB", paper1="#CFE2AE", paper2="#B4CF8E", line="#7FA661", roll0="#4E7A37", roll1="#8DBA68", roll2="#C4DFA0", roll3="#43692F", end0="#D6E9BC", end1="#86AE64", ink="#557F3E")
P.update(dict(a.split('=') for a in sys.argv[1:]))
def roll(x, y, w, h, end_x, flip):
    r = h / 2
    return f'''<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="url(#roll)"/>
    <rect x="{x + r}" y="{y + h * 0.30}" width="{w - 2 * r}" height="{h * 0.12}" rx="{h * 0.06}" fill="#FFFFFF" opacity="0.32"/>
'''
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
<defs>
  <filter id="iconShadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="14" stdDeviation="16" flood-color="#000" flood-opacity="0.28"/></filter>
  <filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="20"/></filter>
  <filter id="softer" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="7"/></filter>
  <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#EDF0E8"/></linearGradient>
  <linearGradient id="paper" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{P['paper0']}"/><stop offset="0.55" stop-color="{P['paper1']}"/><stop offset="1" stop-color="{P['paper2']}"/></linearGradient>
  <linearGradient id="shadeT" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2F4A22" stop-opacity="0.38"/><stop offset="1" stop-color="#2F4A22" stop-opacity="0"/></linearGradient>
  <linearGradient id="shadeB" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#2F4A22" stop-opacity="0.30"/><stop offset="1" stop-color="#2F4A22" stop-opacity="0"/></linearGradient>
  <linearGradient id="roll" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{P['roll0']}"/><stop offset="0.36" stop-color="{P['roll1']}"/><stop offset="0.52" stop-color="{P['roll2']}"/><stop offset="1" stop-color="{P['roll3']}"/></linearGradient>
  <radialGradient id="end" cx="0.4" cy="0.36" r="0.75"><stop offset="0" stop-color="{P['end0']}"/><stop offset="1" stop-color="{P['end1']}"/></radialGradient>
  <clipPath id="sqclip"><path d="{sq}"/></clipPath>
</defs>
<g filter="url(#iconShadow)"><path d="{sq}" fill="url(#bg)"/></g>
<g clip-path="url(#sqclip)">
  <ellipse cx="526" cy="812" rx="250" ry="36" fill="#4D6A38" opacity="0.30" filter="url(#soft)"/>
  <g transform="translate(512 512) rotate(14) scale(1.03)">
    <path d="M-170 -236 C-182 -80 -160 80 -176 236 L176 236 C160 80 182 -80 170 -236 Z" fill="url(#paper)"/>
    <path d="M-170 -236 L-176 -136 L176 -136 L170 -236 Z" fill="url(#shadeT)"/>
    <path d="M-176 236 L-174 150 L174 150 L176 236 Z" fill="url(#shadeB)"/>
    <g stroke="{P['line']}" stroke-opacity="0.42" stroke-width="12" stroke-linecap="round">
      <line x1="-104" y1="-120" x2="112" y2="-120"/><line x1="-106" y1="-58" x2="110" y2="-58"/><line x1="-108" y1="4" x2="64" y2="4"/><line x1="-106" y1="66" x2="106" y2="66"/><line x1="-104" y1="128" x2="30" y2="128"/>
    </g>
    <ellipse cx="0" cy="-226" rx="196" ry="14" fill="#25391A" opacity="0.38" filter="url(#softer)"/>
    {roll(-196, -290, 400, 66, -196, -1)}
    <ellipse cx="0" cy="300" rx="214" ry="16" fill="#25391A" opacity="0.32" filter="url(#softer)"/>
    {roll(-214, 222, 436, 76, 222, 1)}
  </g>
</g>
</svg>'''
open('daf-icon.svg', 'w').write(svg)
