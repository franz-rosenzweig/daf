#!/usr/bin/env python3
"""Daf icon, concept 5 "The hour ring": leaves of paper fanned into a closed circle.

    python3 make.py              # writes v1.svg v2.svg v3.svg, sheet.png and best-1024.png
    python3 make.py explore      # writes explore/*.svg and explore/sheet-*.png

Every variation is one dict of geometry and colour parameters fed to ring().
Angles are clockwise from 12 o'clock. The tile spans 100..924; its centre is (512, 512).
"""
import math, os, sys
sys.path.insert(0, "/srv/dev/daf/design/icon")
import kit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PAL = dict(light="#EAD7B0", mid="#D9BA80", deep="#BC8E52", sepia="#9A5B1F", ink="#7A4614", dark="#3A3127")


def rpoly(pts, rad):
    """Closed polygon with every corner rounded by `rad` (quadratic corners)."""
    n, d = len(pts), ""
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        def toward(a, b, r):
            L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
            r = min(r, L / 2.2)
            return (a[0] + (b[0] - a[0]) * r / L, a[1] + (b[1] - a[1]) * r / L)
        a, b = toward(p1, p0, rad), toward(p1, p2, rad)
        d += f"{'M' if i == 0 else 'L'}{a[0]:.2f},{a[1]:.2f} Q{p1[0]:.2f},{p1[1]:.2f} {b[0]:.2f},{b[1]:.2f} "
    return d + "Z"


def frame(cx, cy, th):
    """Local -> world for a leaf pointing at th degrees: x runs clockwise along the ring, y runs outward."""
    t = math.radians(th)
    u, v = (math.sin(t), -math.cos(t)), (math.cos(t), math.sin(t))
    return lambda x, y: (cx + x * v[0] + y * u[0], cy + x * v[1] + y * u[1])


def leaf_pts(P, r0, R, w_in, w_out, dogear=0):
    pts = [P(-w_in / 2, r0), P(w_in / 2, r0), P(w_out / 2, R)]
    if dogear:   # the outer clockwise corner turned down
        pts = [P(-w_in / 2, r0), P(w_in / 2, r0), P(w_out / 2, R - dogear), P(w_out / 2 - dogear, R)]
    return pts + [P(-w_out / 2, R)]


def ring(p):
    cx, cy, n = p["cx"], p["cy"], p["n"]
    step = 360 / n
    angles = p.get("angles") or [(p.get("rot", 0) + i * step) % 360 for i in range(n)]
    order = p.get("order", "stack")
    sdx, sdy = p.get("shadow", (0, 5))
    corner = p["corner"]
    leaves = []
    for i, th in enumerate(angles):
        tone = p["fill"]
        if p.get("alt"):
            tone = p["alt"][i % len(p["alt"])]
        if p.get("progress") is not None:
            tone = p["done"] if th < p["progress"] * 360 - 1e-6 else p["todo"]
        far = abs(((th - 180) + 180) % 360 - 180)          # 0 at 6 o'clock, 180 at 12
        z = {"stack": far, "top": -far, "cyclic": i, "alt": (i % 2) * 1000 + far}[order]
        if order == "stack" and p.get("bottom_up") and abs(th - 180) < 1:
            z = 999
        l = dict(i=i, th=th, tone=tone, z=z, w=p["w_in"], r0=p["r0"], R=p["R"])
        l.update(p.get("over", {}).get(round(th), {}))
        if not l.get("skip"):
            leaves.append(l)
    leaves.sort(key=lambda l: (l["z"], l["th"]))
    top_i = leaves[-1]["i"]
    if p.get("dogear_at") is not None:
        top_i = next(l["i"] for l in leaves if abs(l["th"] - p["dogear_at"]) < 1)

    laid = []

    def draw(l, clip=""):
        P = frame(cx, cy, l["th"])
        de = p.get("dogear", 0) if (p.get("dogear") and l["i"] == top_i) else 0
        pts = leaf_pts(P, l["r0"], l["R"], l["w"], l["w"] + p["w_out"] - p["w_in"], de)
        s = ""
        if sdx or sdy or p.get("spread"):
            sh = [(x + sdx, y + sdy) for x, y in pts]
            sw = p.get("spread", 0)
            st = f' stroke="{p["shade"]}" stroke-width="{sw}" stroke-linejoin="round"' if sw else ""
            shp = f'<path d="{rpoly(sh, corner)}" fill="{p["shade"]}"{st} opacity="{p.get("shade_op", 1)}"/>'
            if p.get("clip_shadow"):
                cid = f'ringsh{l["i"]}'
                shp = (f'<clipPath id="{cid}">' + "".join(f'<path d="{d}"/>' for d in laid) + '</clipPath>'
                       f'<g clip-path="url(#{cid})">{shp}</g>') if laid else ""
            s += shp
        laid.append(rpoly(pts, corner))
        ol = f' stroke="{p["outline"]}" stroke-width="{p.get("outline_w", 3)}" stroke-linejoin="round"' if p.get("outline") else ""
        s += f'<path d="{rpoly(pts, corner)}" fill="{l["tone"]}"{ol}/>'
        if de:   # the fold: the back of the page, one tone deeper
            fold = [P(p["w_out"] / 2, R - de) for R in [p["R"]]] + [P(p["w_out"] / 2 - de, p["R"] - de), P(p["w_out"] / 2 - de, p["R"])]
            s += f'<path d="{rpoly(fold, 3)}" fill="{p.get("fold", PAL["mid"])}"/>'
        if p.get("edge"):   # fore-edge: a thin band at the outer end showing the page's thickness
            e = p["edge"]
            band = [P(-p["w_out"] / 2, p["R"] - e), P(p["w_out"] / 2, p["R"] - e), P(p["w_out"] / 2, p["R"]), P(-p["w_out"] / 2, p["R"])]
            s += f'<path d="{rpoly(band, 2)}" fill="{p["edge_fill"]}"/>'
        return f'<g{clip}>{s}</g>'

    out = [draw(l) for l in leaves]
    if order == "cyclic":   # leaf 0 lies on leaf n-1: redraw its counter-clockwise half on top
        l0 = next(l for l in leaves if l["i"] == 0)
        P = frame(cx, cy, l0["th"])
        half = [P(0, -50), P(-400, -50), P(-400, 400), P(0, 400)]
        out.append(f'<clipPath id="ringc"><path d="{rpoly(half, 0)}"/></clipPath>')
        out.append(draw(l0, ' clip-path="url(#ringc)"'))
    if p.get("hole"):   # trim every page at the spine so the centre is one clean circle
        h = p["hole"]
        ring_clip = (f'<clipPath id="ringhole"><path clip-rule="evenodd" d="M0,0 H1024 V1024 H0 Z '
                     f'M{cx - h},{cy} a{h},{h} 0 1,0 {2 * h},0 a{h},{h} 0 1,0 {-2 * h},0 Z"/></clipPath>')
        out = [ring_clip, '<g clip-path="url(#ringhole)">'] + out + ['</g>']
    if p.get("hub"):
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{p["hub"]}" fill="{p["hub_fill"]}"/>')
    return "".join(out)


def spine(p):
    """From the spine's end: n leaves radiate from a hollow spine; each is a thin wedge whose upward-facing
    half is lit and whose other half is one tone deeper (light from above, mirror-symmetric, no swirl)."""
    cx, cy, n = p["cx"], p["cy"], p["n"]
    step = 360 / n
    out = []
    for i in range(n):
        th = p.get("rot", 0) + i * step
        if any(abs(((th - a) + 180) % 360 - 180) < 1e-6 for a in p.get("skip", [])):
            continue
        P = frame(cx, cy, th)
        hi, ho = p["w_in"] / 2, p["w_out"] / 2
        a = [P(-hi, p["r0"]), P(0, p["r0"]), P(0, p["R"]), P(-ho, p["R"])]       # counter-clockwise half
        b = [P(0, p["r0"]), P(hi, p["r0"]), P(ho, p["R"]), P(0, p["R"])]         # clockwise half
        t = math.radians(th)
        cw_up = math.sin(t) < -1e-9 or (abs(math.sin(t)) < 1e-9 and math.cos(t) > 0)
        tone = p["fill"]
        if p.get("progress") is not None:
            tone = p["done"] if th < p["progress"] * 360 - 1e-6 else p["todo"]
        lit, dim = (tone, p["dim"].get(tone, p["shade"]))
        fa, fb = (dim, lit) if cw_up else (lit, dim)
        if abs(math.sin(t)) < 1e-9:   # 12 and 6 o'clock: both halves face sideways, keep them lit
            fa = fb = lit
        out.append(f'<path d="{rpoly(a, p["corner"])}" fill="{fa}"/><path d="{rpoly(b, p["corner"])}" fill="{fb}"/>')
    if p.get("hub"):
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{p["hub"]}" fill="{p["hub_fill"]}"/>')
    return "".join(out)


BASE = dict(cx=512, cy=500, corner=5, shade=PAL["sepia"], shade_op=0.8, shadow=(0, 3), spread=3, fill=PAL["mid"],
            order="stack")
SPINE = dict(cx=512, cy=500, view="spine", corner=2, fill=PAL["light"], shade=PAL["mid"],
             dim={PAL["light"]: PAL["mid"], PAL["mid"]: PAL["deep"]})

V = {
    # from above: thirteen pages laid from the bottom up both sides (no swirl); the covers' seam is at 6 o'clock.
    # Pages whose centre lies before 8 o'clock (two-thirds of the way round from 12) are in deeper parchment.
    # The pages are trimmed at the spine (hole) so the centre is one clean circle.
    "v1": dict(BASE, n=13, r0=96, R=268, w_in=124, w_out=124, hole=104,
               progress=2 / 3, done=PAL["mid"], todo=PAL["light"]),
    # from above: eleven broader pages in one tone, no progress; today's page (12 o'clock, on top) has its corner turned
    "v2": dict(BASE, n=11, r0=84, R=268, w_in=148, w_out=148, hole=94, fill=PAL["light"],
               dogear=48, dogear_at=0, fold=PAL["mid"]),
    # from the spine's end: eighteen leaves seen nearly edge-on, the upward-facing side lit
    "v3": dict(SPINE, n=18, r0=106, R=270, w_in=26, w_out=80),
}
NOTES = {
    "v1": "From above: 13 pages stacked up both sides from where the covers meet, round a clean spine; the first two-thirds deeper.",
    "v2": "From above: 11 broader pages in one tone, no progress; today's page at 12 o'clock has its corner turned.",
    "v3": "From the spine's end: 18 leaves edge-on, the side facing up lit. Reads as a paper rosette.",
}

BEST = "v1"

SH = dict(shade=PAL["deep"], shade_op=1, shadow=(0, 4), spread=4)
EX = {
    "e1": dict(BASE, **SH, n=12, r0=96, R=272, w_in=126, w_out=126, order="stack", progress=2 / 3, done=PAL["mid"], todo=PAL["light"]),
    "e2": dict(BASE, **SH, n=12, r0=96, R=272, w_in=126, w_out=126, order="cyclic", progress=2 / 3, done=PAL["mid"], todo=PAL["light"]),
    "e3": dict(BASE, **SH, n=16, r0=80, R=272, w_in=150, w_out=150, order="stack", fill=PAL["light"], dogear=46),
    "e4": dict(BASE, **SH, n=8, r0=168, R=272, w_in=250, w_out=250, order="stack", fill=PAL["light"]),
    "e5": dict(BASE, **SH, n=12, r0=110, R=272, w_in=140, w_out=140, order="stack", fill=PAL["light"], edge=14, edge_fill=PAL["mid"]),
    "e6": dict(BASE, **SH, n=18, r0=150, R=272, w_in=100, w_out=100, order="stack", progress=2 / 3, done=PAL["mid"], todo=PAL["light"]),
}


def build(table, notes, outdir, sheetname):
    os.makedirs(outdir, exist_ok=True)
    svgs = []
    for k, prm in table.items():
        f = os.path.join(outdir, f"{k}.svg")
        open(f, "w").write(kit.tile((spine if prm.get("view") == "spine" else ring)(prm)))
        svgs.append(f)
    kit.sheet(os.path.join(outdir, sheetname), svgs, [k.upper() for k in table], [notes.get(k, "") for k in table])


def main(args):
    if args and args[0] == "explore":
        ks = list(EX)
        for j in range(0, len(ks), 3):
            sub = {k: EX[k] for k in ks[j:j + 3]}
            build(sub, {}, os.path.join(HERE, "explore"), f"sheet-{j // 3 + 1}.png")
        return
    build(V, NOTES, HERE, "sheet.png")
    kit.render(os.path.join(HERE, f"{BEST}.svg"), os.path.join(HERE, "best-1024.png"), 1024)


if __name__ == "__main__":
    main(sys.argv[1:])
