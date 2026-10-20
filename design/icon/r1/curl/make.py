#!/usr/bin/env python3
"""Daf icon, round 1, concept 3: "The curl".

One sheet of parchment, tilted, its top curling back and its bottom curling forward.

How it is drawn: the sheet is a strip of paper whose side view (its profile) is a curve
-- a curl back at the top, a long gently bowed body, a curl forward at the bottom. The
profile is built from arcs as cubic Beziers, turned in 3D (yaw / pitch / roll), and then
swept across the sheet's width. A sweep of a curve along a straight segment is exactly
what a broad-nib pen does, so the whole sheet is one calligrapher's stroke.

Where the profile's tangent runs parallel to the sweep, the paper turns over: those points
split the profile into pieces that show the face (light) or the underside (darker). Each
piece's sweep is one simple closed Bezier shape; drawing them back-to-front is all the
"3D" there is. No gradients, no filters, no outlines: one silhouette and one tint.

    python3 make.py            # v1.svg v2.svg v3.svg, sheet.png, best-1024.png
    python3 make.py v2         # only one variation: v2.svg + a v2-512.png preview
"""
import math
import os
import sys

sys.path.insert(0, "/srv/dev/daf/design/icon")
import kit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

FACE = "#DEC189"      # parchment between "light" and "mid": holds on the white tile, still paper
UNDER = "#BC8E52"     # the underside, where the paper turns toward you ("deep")
INK = "#CCA86E"       # text hints (v3 only): the second tint, between face and underside


# ---------------------------------------------------------------- Bezier helpers

def add(p, q): return tuple(a + b for a, b in zip(p, q))
def sub(p, q): return tuple(a - b for a, b in zip(p, q))
def mul(p, k): return tuple(a * k for a in p)
def lerp(p, q, t): return tuple(a + (b - a) * t for a, b in zip(p, q))
def cross(u, v): return u[0] * v[1] - u[1] * v[0]


def split(seg, t):
    p0, p1, p2, p3 = seg
    a, b, c = lerp(p0, p1, t), lerp(p1, p2, t), lerp(p2, p3, t)
    d, e = lerp(a, b, t), lerp(b, c, t)
    f = lerp(d, e, t)
    return (p0, a, d, f), (f, e, c, p3)


def point(seg, t):
    return split(seg, t)[0][3] if 0 < t < 1 else (seg[0] if t <= 0 else seg[3])


def reverse(seg): return seg[::-1]


# ---------------------------------------------------------------- the profile (side view)

def turtle(start, heading, moves):
    """Arcs in the profile plane (a = depth toward viewer, b = height). moves: (radius, degrees);
    positive degrees turn counter-clockwise; radius None means a straight run of `degrees` px."""
    segs, p, h = [], start, math.radians(heading)
    for r, deg in moves:
        if r is None:
            d = (math.cos(h), math.sin(h))
            q = add(p, mul(d, deg))
            segs.append((p, add(p, mul(d, deg / 3)), add(p, mul(d, 2 * deg / 3)), q))
            p = q
            continue
        total = math.radians(deg)
        n = max(1, math.ceil(abs(total) / (math.pi / 2) - 1e-9))
        sgn = 1 if total > 0 else -1
        nrm = (-math.sin(h), math.cos(h))
        c = add(p, mul(nrm, r * sgn))
        for i in range(n):
            th0 = h + total * i / n
            th1 = h + total * (i + 1) / n
            k = 4 / 3 * math.tan(abs(th1 - th0) / 4) * r
            pt = lambda th: add(c, mul((math.sin(th), -math.cos(th)), r * sgn))  # noqa: E731
            hd = lambda th: (math.cos(th), math.sin(th))  # noqa: E731
            P0, P3 = pt(th0), pt(th1)
            segs.append((P0, add(P0, mul(hd(th0), k)), sub(P3, mul(hd(th1), k)), P3))
        h += total
        p = segs[-1][3]
    return segs, p, math.degrees(h)


def profile(g):
    """The whole profile from the bottom free edge to the top free edge."""
    body, end, h_end = turtle((0.0, 0.0), 90, g["body"])
    top, _, _ = turtle(end, h_end, g["top"])            # turns left = back
    bottom, _, _ = turtle((0.0, 0.0), 90 + 180, g["bottom"])  # heading down, turns left = forward
    return [reverse(s) for s in reversed(bottom)] + body + top


# ---------------------------------------------------------------- 3D turn and projection

def rotation(yaw, pitch, roll):
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    cr, sr = math.cos(math.radians(roll)), math.sin(math.radians(roll))

    def R(v):
        x, y, z = v
        x, z = x * cy + z * sy, -x * sy + z * cy         # yaw about the vertical
        y, z = y * cp - z * sp, y * sp + z * cp          # pitch: + looks from above
        x, y = x * cr - y * sr, x * sr + y * cr          # roll: in-plane tilt (y up, CCW)
        return (x, y, z)
    return R


def build(g):
    """-> list of layers (depth, fill, path-segments) in screen space (y up), plus extras."""
    R = rotation(g["yaw"], g["pitch"], g["roll"])
    prof3 = [tuple(R((0.0, b, a)) for (a, b) in seg) for seg in profile(g)]
    X = R((1.0, 0.0, 0.0))
    X2 = (X[0], X[1])

    # split where the tangent is parallel to the sweep: there the paper turns over
    pieces, cur, cur_sign = [], [], None
    for seg in prof3:
        P = [(p[0], p[1]) for p in seg]
        c0, c1, c2 = (cross(X2, sub(P[i + 1], P[i])) for i in range(3))
        A, B, C = c0 - 2 * c1 + c2, 2 * (c1 - c0), c0
        roots = []
        if abs(A) < 1e-9:
            if abs(B) > 1e-9:
                roots = [-C / B]
        else:
            disc = B * B - 4 * A * C
            if disc >= 0:
                s = math.sqrt(disc)
                roots = sorted([(-B - s) / (2 * A), (-B + s) / (2 * A)])
        roots = [t for t in roots if 1e-4 < t < 1 - 1e-4]
        subs, rest, t_prev = [], seg, 0.0
        for t in roots:
            a, rest = split(rest, (t - t_prev) / (1 - t_prev))
            subs.append(a)
            t_prev = t
        subs.append(rest)
        for s3 in subs:
            q = [(p[0], p[1]) for p in s3]
            d = [sub(q[i + 1], q[i]) for i in range(3)]
            mid = add(add(mul(d[0], 0.25), mul(d[1], 0.5)), mul(d[2], 0.25))  # tangent at t=.5 (/3)
            sign = 1 if cross(X2, mid) > 0 else -1
            if sign != cur_sign and cur:
                pieces.append((cur_sign, cur))
                cur = []
            cur_sign = sign
            cur.append(s3)
    pieces.append((cur_sign, cur))

    half = mul(X2, g["width"] / 2)
    layers = []
    for sign, segs in pieces:
        flat = [tuple((p[0], p[1]) for p in s) for s in segs]
        depth = sum(p[2] for s in segs for p in s) / (4 * len(segs))
        left = [tuple(sub(p, half) for p in s) for s in flat]
        right = [tuple(add(p, half) for p in s) for s in flat]
        line_a = (left[-1][3], lerp(left[-1][3], right[-1][3], 1 / 3), lerp(left[-1][3], right[-1][3], 2 / 3), right[-1][3])
        line_b = (right[0][0], lerp(right[0][0], left[0][0], 1 / 3), lerp(right[0][0], left[0][0], 2 / 3), left[0][0])
        ring = left + [line_a] + [reverse(s) for s in reversed(right)] + [line_b]
        layers.append({"depth": depth, "fill": FACE if sign > 0 else UNDER, "segs": ring, "front": sign > 0})
    layers.sort(key=lambda L: L["depth"])

    # a quiet hint of text: short lines across the body, parallel to the sweep
    lines = []
    if g.get("lines"):
        body3 = [tuple(R((0.0, b, a)) for (a, b) in seg) for seg in turtle((0.0, 0.0), 90, g["body"])[0]]
        n_lines, b0, b1, margin = g["lines"]
        L = sum(math.dist(s[0][:2], s[3][:2]) for s in body3)
        for i in range(n_lines):
            f = b0 + (b1 - b0) * i / max(1, n_lines - 1)
            # walk to arc-length fraction f of the body
            target, acc = f * L, 0.0
            for s in body3:
                ln = math.dist(s[0][:2], s[3][:2])
                if acc + ln >= target:
                    p = point(s, (target - acc) / ln)
                    break
                acc += ln
            w = g["width"] / 2 - margin
            short = g.get("line_short", {}).get(i, 0)   # i = 0 is the lowest line
            if g.get("rtl"):                              # Hebrew paragraph: last line hugs the right
                a, b = sub(p[:2], mul(X2, w - short)), add(p[:2], mul(X2, w))
            else:
                a, b = sub(p[:2], mul(X2, w)), add(p[:2], mul(X2, w - short))
            lines.append((a, b))
    return layers, lines


# ---------------------------------------------------------------- organic warp and placement

def place(layers, lines, g):
    """Gentle bow across the sheet (so no edge is ruler-straight), then fit into the tile."""
    bow = g.get("bow", 0.0)
    roll = math.radians(g["roll"])
    ux, uy = math.cos(roll), math.sin(roll)        # across the sheet (screen, y up)
    vx, vy = -uy, ux                               # along the sheet

    def warp(p):
        u = p[0] * ux + p[1] * uy
        w = g["width"] * 0.62
        k = bow * (1 - (u / w) ** 2)               # middle of each across-line sags/lifts
        return (p[0] + vx * k, p[1] + vy * k)

    for L in layers:
        L["segs"] = [tuple(warp(p) for p in s) for s in L["segs"]]
    lines = [tuple(warp(p) for p in ln) for ln in lines]

    pts = [point(s, t / 12) for L in layers for s in L["segs"] for t in range(13)]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    scale = g["size"] / max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ox, oy = 512 + g.get("dx", 0), g.get("cy", 502)

    def T(p):
        return (ox + (p[0] - cx) * scale, oy - (p[1] - cy) * scale)   # y down for SVG

    for L in layers:
        L["segs"] = [tuple(T(p) for p in s) for s in L["segs"]]
    lines = [tuple(T(p) for p in ln) for ln in lines]
    return layers, lines, scale


def path_d(segs):
    f = lambda p: f"{p[0]:.1f} {p[1]:.1f}"  # noqa: E731
    d = [f"M{f(segs[0][0])}"]
    for s in segs:
        d.append(f"C{f(s[1])} {f(s[2])} {f(s[3])}")
    return " ".join(d) + "Z"


def svg(g):
    layers, lines = build(g)
    layers, lines, scale = place(layers, lines, g)
    out = []
    for L in layers:                               # back to front
        out.append(f'<path fill="{L["fill"]}" d="{path_d(L["segs"])}"/>')
        if L["front"] and lines:                   # text sits on the face, under the forward curl
            sw = g.get("line_w", 16) * scale
            for a, b in lines:
                out.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                           f'stroke="{INK}" stroke-width="{sw:.1f}" stroke-linecap="round"/>')
            lines = []
    return kit.tile("".join(out))


# ---------------------------------------------------------------- the three variations
# body / top / bottom: (radius, degrees) arcs in the profile plane; None radius = straight run.
# Curls tighten toward the free edge (like real paper), and never pass a half turn and a bit.

V = {
    "v1": dict(
        note="Wide leaf leaning right, a soft S in the body; a rounded back-lip on top, a full forward curl at the foot.",
        width=470, size=548, roll=-14, yaw=34, pitch=10, bow=28,
        body=[(950, 9.5), (950, -9.5)],
        top=[(104, 95), (64, 85)],
        bottom=[(96, 90), (62, 115)],
    ),
    "v2": dict(
        note="Narrow sheet, steep lean, deeper curls both ends: the most stroke-like, the least page-like.",
        width=360, size=548, roll=-24, yaw=46, pitch=12, bow=16,
        body=[(1000, 10), (1000, -10)],
        top=[(86, 90), (56, 110)],
        bottom=[(92, 90), (60, 120)],
    ),
    "v3": dict(
        note="Mirrored lean, straight body, three quiet lines of text set right-to-left (the short last line hugs the right).",
        width=470, size=548, roll=14, yaw=-34, pitch=10, bow=22,
        body=[(None, 380)],
        top=[(96, 95), (60, 85)],
        bottom=[(90, 90), (58, 115)],
        lines=(3, 0.30, 0.84, 78), line_w=18, line_short={0: 140}, rtl=True,
    ),
}


BEST = "v1"


def main(only=None):
    names = [only] if only else list(V)
    for n in names:
        open(os.path.join(HERE, f"{n}.svg"), "w").write(svg(V[n]))
        if only:
            kit.render(os.path.join(HERE, f"{n}.svg"), os.path.join(HERE, f"{n}-512.png"), 512)
    if not only:
        kit.sheet(os.path.join(HERE, "sheet.png"), [os.path.join(HERE, f"{n}.svg") for n in V],
                  [n.upper() for n in V], [V[n]["note"] for n in V])
        kit.render(os.path.join(HERE, f"{BEST}.svg"), os.path.join(HERE, "best-1024.png"), 1024)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
