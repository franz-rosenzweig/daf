#!/usr/bin/env python3
"""Daf icon, round 1, concept 4: the ribbon.

A silk marker ribbon lying across the edge of a parchment leaf, its tail hanging free and
ending in a cut. Flat shapes: the silk has exactly two tones (front, back), the paper is
parchment, and the only soft thing is the ribbon's contact shadow on the paper.

    python3 make.py              # v1.svg v2.svg v3.svg, sheet.png, best-1024.png
    python3 make.py --svg        # SVGs only

How it is drawn: the leaf and the ribbon are modelled in 3D (a leaf is a thin box; the
ribbon is a centreline of cubic Béziers with a width vector carried along it and a twist
profile), projected orthographically, and written out as flat 2D shapes. The ribbon's two
edges become cubic Béziers (Catmull-Rom handles); where the silk turns edge-on the shape is
split and the far side is filled with the back tone.
"""
import math, os, sys

import numpy as np

sys.path.insert(0, "/srv/dev/daf/design/icon")
import kit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

PARCH = {"light": "#EAD7B0", "mid": "#D9BA80", "deep": "#BC8E52"}
SILK = {                                   # front, back of the silk
    "sepia":   ("#9A5B1F", "#7A4614"),
    "blue":    ("#1A7DA4", "#135C7A"),
    "oxblood": ("#7C2229", "#55161B"),
}
SHADOW_INK = "#4A2C0E"


# ---------------------------------------------------------------- 2D output
def fmt(p):
    return f"{p[0]:.1f},{p[1]:.1f}"


def curve_d(pts, move=True):
    """Catmull-Rom through pts, written as cubic Béziers ('M p0 C ...' or just the 'C ...' part)."""
    d = ["M" + fmt(pts[0])] if move else []
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < n else pts[i + 1]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{fmt(c1)} {fmt(c2)} {fmt(p2)}")
    return " ".join(d)


def thin(pts, gap):
    """Keep points about `gap` px apart along the chain (always the first and last)."""
    if len(pts) <= 2:
        return list(pts)
    out, acc = [pts[0]], 0.0
    for a, b in zip(pts, pts[1:]):
        acc += math.hypot(b[0] - a[0], b[1] - a[1])
        if acc >= gap:
            out.append(b)
            acc = 0.0
    if out[-1] is not pts[-1]:
        if len(out) > 1 and math.hypot(out[-1][0] - pts[-1][0], out[-1][1] - pts[-1][1]) < gap * 0.5:
            out[-1] = pts[-1]
        else:
            out.append(pts[-1])
    return out


def poly_d(pts):
    return "M" + " L".join(fmt(p) for p in pts) + " Z"


def smoothstep(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def keyed(keys, s):
    """Piecewise smoothstep through (position, value) keys."""
    if s <= keys[0][0]:
        return keys[0][1]
    for (s0, v0), (s1, v1) in zip(keys, keys[1:]):
        if s <= s1:
            return v0 + (v1 - v0) * smoothstep((s - s0) / (s1 - s0) if s1 > s0 else 1)
    return keys[-1][1]


# ---------------------------------------------------------------- 3D
def V(*a):
    return np.array(a, dtype=float)


def norm(v):
    return v / (np.linalg.norm(v) or 1)


class Camera:
    """Orthographic camera: az turns the scene about the vertical axis, el tilts it toward us
    (we look down on it). World: x right, y up, z toward the viewer."""

    def __init__(self, az=0, el=0, scale=1.0, at=(512, 500), origin=(0, 0, 0)):
        a, e = math.radians(az), math.radians(el)
        Ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
        Rx = np.array([[1, 0, 0], [0, math.cos(e), -math.sin(e)], [0, math.sin(e), math.cos(e)]])
        self.R = Rx @ Ry
        self.s, self.at, self.o = scale, at, np.array(origin, float)

    def p(self, X):
        q = self.R @ (np.asarray(X, float) - self.o)
        return (self.at[0] + self.s * q[0], self.at[1] - self.s * q[1])

    def z(self, X):
        return (self.R @ (np.asarray(X, float) - self.o))[2]

    def facing(self, n):
        return (self.R @ n)[2]


def bez3(p0, p1, p2, p3, n=60):
    t = np.linspace(0, 1, n)[:, None]
    u = 1 - t
    return u**3 * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t**3 * p3


def leg_line(a, b):
    return (a, a + (b - a) / 3, a + (b - a) * 2 / 3, b)


def legs_through(start, d0, anchors):
    """Cubic legs from `start` (leaving in direction d0) through 3D anchors (Catmull-Rom)."""
    pts = [start] + list(anchors)
    legs = []
    for i in range(len(pts) - 1):
        p1, p2 = pts[i], pts[i + 1]
        if i == 0:
            t1 = d0 * np.linalg.norm(p2 - p1)
        else:
            t1 = (p2 - pts[i - 1]) * 0.5
        t2 = (pts[i + 2] - p1) * 0.5 if i + 2 < len(pts) else (p2 - p1)
        legs.append((p1, p1 + t1 / 3, p2 - t2 / 3, p2))
    return legs


def sample_legs(legs, step=2.0):
    pts = []
    for i, L in enumerate(legs):
        q = bez3(*L, n=80)
        pts.extend(q if i == 0 else q[1:])
    pts = np.array(pts)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    keep = np.concatenate([[True], seg > 1e-9])
    pts = pts[keep]
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1]
    s = np.linspace(0, total, max(3, int(total / step)))
    out = np.stack([np.interp(s, cum, pts[:, k]) for k in range(3)], axis=1)
    return out, s


# ---------------------------------------------------------------- the ribbon
def _trim(chain, side, want, from_end):
    """Drop the run of points at one end of a 2D chain that lies on the wrong side of a line
    (side(q) has the wrong sign), ending the chain exactly on the line instead."""
    pts = list(reversed(chain)) if from_end else list(chain)
    i = 0
    while i < len(pts) - 2 and side(pts[i]) * want < 0:
        i += 1
    if i > 0:
        a, b = pts[i - 1], pts[i]
        sa_, sb_ = side(a), side(b)
        t = sa_ / (sa_ - sb_) if sa_ != sb_ else 0
        x = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        pts = [x] + pts[i:]
    return list(reversed(pts)) if from_end else pts


def ribbon(cam, legs, W0, width, twist=((0, 0),), end="swallow", notch=0.45, cut=0.0, step=2.0, gap=9.0, crease=True):
    """Project a ribbon. Returns ([(face, d, depth)] in drawing order, far first; centreline; edges).

    legs    cubic legs of the centreline (3D)
    W0      the width direction at the start (3D)
    twist   (distance along in px, degrees) keys; negative distances count from the end
    end     'swallow' (notch = depth as a fraction of width), 'angle' (cut = how much shorter
            one edge is, as a fraction of width; negative cuts the other edge), 'flat'
    """
    C, s = sample_legs(legs, step)
    L = s[-1]
    keys = [((k if k >= 0 else L + k), v) for k, v in twist]
    N = len(C)
    T = np.gradient(C, axis=0)
    T = T / np.linalg.norm(T, axis=1)[:, None]
    # width vector carried along the curve without spin (rotation-minimising), then twisted
    W = np.zeros_like(C)
    w = norm(W0 - T[0] * np.dot(W0, T[0]))
    for i in range(N):
        w = norm(w - T[i] * np.dot(w, T[i]))
        W[i] = w
    Wt = np.zeros_like(W)
    for i in range(N):
        a = math.radians(keyed(keys, s[i]))
        Wt[i] = W[i] * math.cos(a) + np.cross(T[i], W[i]) * math.sin(a)
    Ep = C + Wt * width / 2
    Em = C - Wt * width / 2
    face = np.array([cam.facing(np.cross(T[i], Wt[i])) for i in range(N)])

    # runs of one face
    runs = []
    cur = {"front": face[0] >= 0, "P": [Ep[0]], "M": [Em[0]], "C": [C[0]]}
    for i in range(1, N):
        f = face[i] >= 0
        if f != cur["front"]:
            t = face[i - 1] / (face[i - 1] - face[i])
            xp, xm, xc = Ep[i - 1] + (Ep[i] - Ep[i - 1]) * t, Em[i - 1] + (Em[i] - Em[i - 1]) * t, C[i - 1] + (C[i] - C[i - 1]) * t
            cur["P"].append(xp); cur["M"].append(xm); cur["C"].append(xc)
            runs.append(cur)
            cur = {"front": f, "P": [xp], "M": [xm], "C": [xc]}
        cur["P"].append(Ep[i]); cur["M"].append(Em[i]); cur["C"].append(C[i])
    runs.append(cur)

    # project, then trim the thin fold-over slivers so neighbouring faces meet on a clean crease
    for r in runs:
        r["p"] = [cam.p(x) for x in r["P"]]
        r["m"] = [cam.p(x) for x in r["M"]]
        r["c"] = [cam.p(x) for x in r["C"]]
    if crease:
        for k in range(len(runs) - 1):
            a, b = runs[k], runs[k + 1]
            l0, l1 = np.array(a["p"][-1]), np.array(a["m"][-1])      # the edge-on ruling
            d = l1 - l0
            nrm = np.array([-d[1], d[0]])
            side = lambda q: float(np.dot(np.array(q) - l0, nrm))
            sa = side(a["c"][max(0, len(a["c"]) - 15)])
            sb = side(b["c"][min(len(b["c"]) - 1, 14)])
            for key in ("p", "m"):
                a[key] = _trim(a[key], side, sa, from_end=True)
                b[key] = _trim(b[key], side, sb, from_end=False)

    out = []
    for k, r in enumerate(runs):
        P, M = r["p"], r["m"]
        last = k == len(runs) - 1
        if last and end == "swallow":
            tip = cam.p(C[-1] - T[-1] * notch * width)
            rm = list(reversed(thin(M, gap)))
            d = curve_d(thin(P, gap)) + f" L{fmt(tip)} L{fmt(rm[0])} " + curve_d(rm, move=False) + " Z"
        else:
            if last and end == "angle" and cut:
                drop = max(1, int(abs(cut) * width / step))
                if cut > 0:
                    M = M[:-drop]
                else:
                    P = P[:-drop]
            rm = list(reversed(thin(M, gap)))
            d = curve_d(thin(P, gap)) + f" L{fmt(rm[0])} " + curve_d(rm, move=False) + " Z"
        out.append({"face": "front" if r["front"] else "back", "d": d,
                    "z": float(np.mean([cam.z(x) for x in r["C"]])),
                    "zhead": float(np.mean([cam.z(x) for x in r["C"][:12]])),
                    "ztail": float(np.mean([cam.z(x) for x in r["C"][-12:]]))})
    # order: at each fold the nearer side is drawn later
    rank = [0.0]
    for k in range(1, len(out)):
        rank.append(rank[-1] + (1 if out[k]["zhead"] > out[k - 1]["ztail"] else -1))
    order = sorted(range(len(out)), key=lambda k: rank[k])
    return [(out[k]["face"], out[k]["d"], out[k]["z"]) for k in order], C, Ep, Em


def seamed(cam, legs, W0, width, seam, end="swallow", notch=0.45, cut=0.0, step=2.0, gap=9.0):
    """A ribbon whose half-turn is drawn the way an illustrator draws it: the silk narrows a
    little at a waist and the two faces meet on one clean diagonal crease.

    seam    (centre, length, waist, dir): centre in px along the ribbon (negative = from the
            end), length of the crease along the ribbon, waist = how much it narrows there
            (0..1), dir = +1 if the crease runs from the minus edge forward to the plus edge.
    """
    C, s = sample_legs(legs, step)
    L = s[-1]
    T = np.gradient(C, axis=0)
    T = T / np.linalg.norm(T, axis=1)[:, None]
    W = np.zeros_like(C)
    w = norm(W0 - T[0] * np.dot(W0, T[0]))
    for i in range(len(C)):
        w = norm(w - T[i] * np.dot(w, T[i]))
        W[i] = w
    Ep, Em = C + W * width / 2, C - W * width / 2
    c2 = np.array([cam.p(x) for x in C])
    p2 = np.array([cam.p(x) for x in Ep])
    m2 = np.array([cam.p(x) for x in Em])
    pos, length, waist, sdir = seam
    pos = pos if pos >= 0 else L + pos
    k = 1 - waist * np.exp(-((s - pos) / (length * 0.75)) ** 2)
    p2 = c2 + (p2 - c2) * k[:, None]
    m2 = c2 + (m2 - c2) * k[:, None]
    ia = int(np.searchsorted(s, pos - length / 2))
    ib = int(np.searchsorted(s, pos + length / 2))
    lo, hi = (m2, p2) if sdir > 0 else (p2, m2)     # the crease leaves `lo` at ia, meets `hi` at ib
    T2 = np.gradient(c2, axis=0)
    T2 = T2 / np.linalg.norm(T2, axis=1)[:, None]

    def chain(a, i0, i1):
        return [tuple(q) for q in a[i0:i1 + 1]]
    # front: everything before the crease
    f_hi = chain(hi, 0, ib)
    f_lo = chain(lo, 0, ia)
    d_front = curve_d(thin(f_hi, gap)) + f" L{fmt(f_lo[-1])} " + curve_d(list(reversed(thin(f_lo, gap))), move=False) + " Z"
    # back: from the crease to the end
    b_hi = chain(hi, ib, len(hi) - 1)
    b_lo = chain(lo, ia, len(lo) - 1)
    if end == "angle" and cut:
        drop = max(1, int(abs(cut) * width * cam.s / (step * cam.s)))
        if (cut > 0) == (sdir > 0):
            b_lo = b_lo[:-drop]
        else:
            b_hi = b_hi[:-drop]
    tipd = ""
    if end == "swallow":
        tip = tuple(c2[-1] - T2[-1] * notch * width * cam.s)
        tipd = f" L{fmt(tip)}"
    d_back = (curve_d(thin(b_lo, gap)) + tipd + f" L{fmt(b_hi[-1])} " + curve_d(list(reversed(thin(b_hi, gap))), move=False) + " Z")
    z = float(np.mean([cam.z(x) for x in C]))
    return [("front", d_front, z), ("back", d_back, z)], C, Ep, Em


# ---------------------------------------------------------------- the leaf
def leaf_box(cam, O, u, v, n, W, H, t):
    """A leaf (or thin stack of leaves): front face at O + a*u + b*v (0<=a<=W, 0<=b<=H),
    thickness t behind it along -n. Returns visible faces as (kind, 2D points, depth, 3D points), far first."""
    O, u, v, n = map(np.asarray, (O, u, v, n))
    f = [O, O + u * W, O + u * W + v * H, O + v * H]
    b = [p - n * t for p in f]
    faces = {
        "front": (f, n), "back": (b[::-1], -n),
        "top": ([b[0], b[1], f[1], f[0]], -v), "bottom": ([f[3], f[2], b[2], b[3]], v),
        "left": ([b[0], f[0], f[3], b[3]], -u), "right": ([f[1], b[1], b[2], f[2]], u),
    }
    vis = []
    for k, (pts, nn) in faces.items():
        if cam.facing(nn) > 1e-6:
            vis.append((k, [cam.p(p) for p in pts], float(np.mean([cam.z(p) for p in pts])), pts))
    vis.sort(key=lambda x: x[2])
    return vis


# ---------------------------------------------------------------- one icon
def icon(v):
    """v: a dict built by build(). Returns the whole SVG."""
    name = v["name"]
    front, back = SILK[v["silk"]]
    defs = (f'<filter id="{name}-blur" x="-30%" y="-30%" width="160%" height="160%">'
            f'<feGaussianBlur stdDeviation="{v.get("blur", 7):.1f}"/></filter>'
            f'<clipPath id="{name}-paper">' + "".join(f'<path d="{d}"/>' for _, d in v["paper"]) + '</clipPath>')
    if v.get("ribbon_clip"):
        defs += f'<clipPath id="{name}-rclip"><path d="{v["ribbon_clip"]}"/></clipPath>'
    sx, sy = v.get("shadow_offset", (4, 9))
    shadow = (f'<g clip-path="url(#{name}-paper)"><g filter="url(#{name}-blur)" opacity="{v.get("shadow_opacity", 0.32)}" '
              f'transform="translate({sx:.1f} {sy:.1f})">' + "".join(f'<path d="{d}" fill="{SHADOW_INK}"/>' for _, d, _ in v["pieces"]) + "</g></g>")
    rib = "".join(f'<path d="{d}" fill="{front if f == "front" else back}"/>' for f, d, _ in v["pieces"])
    if v.get("ribbon_clip"):
        rib = f'<g clip-path="url(#{name}-rclip)">{rib}</g>'
        shadow = f'<g clip-path="url(#{name}-rclip)">{shadow}</g>'
    paper = "".join(f'<path d="{d}" fill="{c}"/>' for c, d in v["paper"])
    return kit.tile(paper + shadow + rib, defs)


def half_plane(a, b, inside):
    """A big 2D polygon on the side of line ab that contains `inside`."""
    a, b, inside = np.asarray(a), np.asarray(b), np.asarray(inside)
    u = norm(b - a)
    nrm = np.array([-u[1], u[0]])
    if np.dot(inside - a, nrm) < 0:
        nrm = -nrm
    A, B = a - u * 3000, a + u * 3000
    return poly_d([A, B, B + nrm * 3000, A + nrm * 3000])


def bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------- the scene
def leaf_scene(p, cam):
    """A leaf standing tilted back (a page on a reading stand), turned in its own plane by
    `turn` degrees; the ribbon comes over its top edge, lies down the page, goes over the
    bottom edge and hangs, with a half-turn and a cut end."""
    W, H, t = p["W"], p["H"], p["t"]
    b = math.radians(p["tilt"])           # leaning back from vertical
    g = math.radians(p["turn"])           # turned in its own plane
    n = V(0, math.sin(b), math.cos(b))
    down0 = V(0, -math.cos(b), math.sin(b))
    right0 = V(1, 0, 0)
    u = right0 * math.cos(g) + down0 * math.sin(g)
    v = -right0 * math.sin(g) + down0 * math.cos(g)
    O = -u * W / 2 - v * H / 2              # page centred on the origin
    faces = leaf_box(cam, O, u, v, n, W, H, t)

    lift = n * 0.5

    def on(a_, b_):
        return O + u * (a_ * W) + v * (b_ * H) + lift
    path = p.get("path") or [(p["at"], 0), (p["at"] + p.get("sway", 0), 0.5), (p["at"], 1)]
    first = on(*path[0])
    edge = p.get("start_edge", "top")
    inward = v if edge == "top" else u
    legs = [leg_line(first - n * t, first)]          # the silk comes over the edge from behind
    legs += legs_through(first, inward, [on(*q) for q in path[1:]])
    # the free tail, leaving the last edge and falling under its own weight
    last = on(*path[-1])
    d_out = norm(on(*path[-1]) - on(*path[-2]))
    anchors = [last + d_out * q[0] + V(*q[1:]) if len(q) == 4 else last + V(*q) for q in p["tail"]]
    legs += legs_through(last, d_out, anchors)
    if p.get("seam"):
        pieces, C, Ep, Em = seamed(cam, legs, u, p["width"], p["seam"], p["end"], p.get("notch", 0.45), p.get("cut", 0.0))
    else:
        pieces, C, Ep, Em = ribbon(cam, legs, u, p["width"], p["twist"], p["end"], p.get("notch", 0.45), p.get("cut", 0.0))
    if edge == "top":
        tb = [cam.p(O - n * t), cam.p(O + u * W - n * t)]
    else:
        tb = [cam.p(O - n * t), cam.p(O + v * H - n * t)]
    clip = half_plane(tb[0], tb[1], cam.p(V(0, 0, 0)))
    return faces, pieces, clip, [cam.p(x) for x in C] + [cam.p(x) for x in Ep] + [cam.p(x) for x in Em]


def build(p):
    """Two passes: lay the scene out, then scale and place it so the object's larger side is
    `fill` of the 824 px tile and its box centres on (512 + dx, cy)."""
    cam = Camera(p["az"], p["el"], 1.0, (0, 0))
    faces, pieces, clip, rpts = leaf_scene(p, cam)
    allpts = rpts + [q for f in faces for q in f[1]]
    x0, y0, x1, y1 = bbox(allpts)
    s = p.get("fill", 0.64) * 824 / max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    at = (512 - s * cx + p.get("dx", 0), p.get("cy", 504) - s * cy)
    cam = Camera(p["az"], p["el"], s, at)
    faces, pieces, clip, rpts = leaf_scene(p, cam)
    colours = dict({"front": PARCH["light"]}, **p.get("faces", {}))
    paper = [(colours.get(k, PARCH["mid"]), poly_d(pts)) for k, pts, _, _ in faces]
    # the leaves of a thin stack: fine light lines along the visible edges
    marks = []
    for k, pts2, _, pts3 in faces:
        if k in ("front", "back") or not p.get("leaves"):
            continue
        a0, a1, b1, b0 = pts3                 # make a0-a1 and b0-b1 the two long edges
        if np.linalg.norm(a1 - a0) < np.linalg.norm(b0 - a0):
            a0, a1, b1, b0 = a1, b1, b0, a0
        for j in range(1, p["leaves"]):
            f = j / p["leaves"]
            q0, q1 = a0 + (b0 - a0) * f, a1 + (b1 - a1) * f
            lw = p.get("leaf_line", 1.6) / 2 / s
            off = (b0 - a0) / (np.linalg.norm(b0 - a0) or 1) * lw
            marks.append((PARCH["light"], poly_d([cam.p(q0 - off), cam.p(q1 - off), cam.p(q1 + off), cam.p(q0 + off)])))
    paper += marks
    allpts = rpts + [q for f in faces for q in f[1]]
    return dict(name=p["name"], silk=p["silk"], paper=paper, pieces=pieces, ribbon_clip=clip, box=bbox(allpts),
                blur=p.get("blur", 6) * s, shadow_offset=(p.get("sx", 3) * s, p.get("sy", 7) * s),
                shadow_opacity=p.get("so", 0.32), scale=s)


# ---------------------------------------------------------------- the variations
BASE = dict(W=330, H=420, t=10, tilt=14, turn=-9, az=-16, el=10, at=0.66, width=62,
            tail=((4, -80, 14), (26, -160, 30), (14, -240, 36)), twist=((0, 0), (-160, 0), (-80, 180)),
            end="swallow", notch=0.42, fill=0.64, cy=504)


def v1():
    return build(dict(BASE, name="rb1", silk="sepia"))


def v2():
    return build(dict(BASE, name="rb2", silk="blue", turn=8, at=0.32, end="angle", cut=0.9))


def v3():
    return build(dict(BASE, name="rb3", silk="oxblood"))


VARIANTS = [v1, v2, v3]
NOTES = [
    "Sepia silk over the bottom edge of a leaf; half-turn, swallow-tail.",
    "Blue silk; angled cut.",
    "Oxblood silk.",
]


def write_all(dirpath=HERE, fns=VARIANTS, prefix="v"):
    out = []
    for i, fn in enumerate(fns, 1):
        pth = os.path.join(dirpath, f"{prefix}{i}.svg")
        open(pth, "w").write(icon(fn()))
        out.append(pth)
    return out


if __name__ == "__main__":
    svgs = write_all()
    if "--svg" in sys.argv:
        sys.exit()
    kit.sheet(os.path.join(HERE, "sheet.png"), svgs, ["V1", "V2", "V3"], NOTES)
    if "--sheet" not in sys.argv:
        best = int(os.environ.get("BEST", "1"))
        kit.render(svgs[best - 1], os.path.join(HERE, "best-1024.png"), 1024)
