"""The folio: one parchment leaf with a corner turned up to show its back (amud bet).

    python3 make.py            # writes v1.svg v2.svg v3.svg, sheet.png, best-1024.png

Technique: flat shapes, one restrained gradient on the turned corner only, a crisp contact
shadow plus a soft ambient shadow under the leaf. One light, from above.
"""
import math, os, sys
sys.path.insert(0, "/srv/dev/daf/design/icon")
import kit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

BASE = dict(
    w=420, h=556,            # leaf size (portrait, about a Gemara folio's 1:1.32)
    cx=512, cy=498,          # leaf centre on the tile (visual centre sits above 512)
    rot=0,                   # whole-leaf tilt, degrees
    mirror=False,            # False = bottom-left corner turned (the Hebrew way); True = bottom-right
    radii=(30, 18, 22), taper=0,      # leaf corners: top-left, top-right, bottom-right (parchment is never square)
    a=270, c=320,            # fold: distance from the corner along the bottom edge (a) and up the side (c)
    curl=0.80,               # how far the tip travels towards a flat fold (1 = flat crease)
    bow_a=-0.06, bow_c=0.12, # how much the flap's two outer edges bow outwards (<0 inwards)
    roll=12,                 # how far the rolled fold bulges past the cut
    tipr=10,                 # roundness of the flap tip
    wave=2.2,                # parchment: gentle unevenness of the edges, px
    face="#EAD7B0",
    back=("#A8773F", "#CFA96B", "#DDBF88"),   # flap gradient: at the fold, middle, at the tip
    stops=(0.0, 0.4, 1.0),
    ink="#3A3127",           # shadow colour
    flap_shadow=0.30, fs_dx=8, fs_dy=10,
    contact=0.32, ambient=0.18,
    lit=(5, "#F4E4C2", 0.9),  # the one lit edge: width (px, half of it shows), colour, opacity
)


def rot(p, deg):
    t = math.radians(deg)
    return (p[0] * math.cos(t) - p[1] * math.sin(t), p[0] * math.sin(t) + p[1] * math.cos(t))


def wavy(p0, p1, n, amp, seed):
    """Points from p0 to p1 (exclusive of p1), nudged perpendicular by a low, uneven wave."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L, dx / L
    pts = []
    for i in range(n):
        t = i / n
        env = math.sin(math.pi * t) ** 2
        off = amp * env * (0.7 * math.sin(2 * math.pi * (0.9 * t + seed)) + 0.3 * math.sin(2 * math.pi * (1.7 * t + 2 * seed)))
        pts.append((p0[0] + dx * t + nx * off, p0[1] + dy * t + ny * off))
    return pts


def arc(c, r, a0, a1, n=8):
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n)]


def fmt(pts):
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"


def fillet(V, Vp, Vn, r, n=14):
    """Arc of radius r rounding the corner V between neighbours Vp and Vn (sampled points)."""
    if r <= 0:
        return [V], V, V
    ux, uy = Vp[0] - V[0], Vp[1] - V[1]; lu = math.hypot(ux, uy); ux, uy = ux / lu, uy / lu
    vx, vy = Vn[0] - V[0], Vn[1] - V[1]; lv = math.hypot(vx, vy); vx, vy = vx / lv, vy / lv
    th = math.acos(max(-1, min(1, ux * vx + uy * vy)))
    d = r / math.tan(th / 2)
    t1 = (V[0] + ux * d, V[1] + uy * d); t2 = (V[0] + vx * d, V[1] + vy * d)
    bx, by = ux + vx, uy + vy; lb = math.hypot(bx, by); bx, by = bx / lb, by / lb
    O = (V[0] + bx * r / math.sin(th / 2), V[1] + by * r / math.sin(th / 2))
    a1 = math.atan2(t1[1] - O[1], t1[0] - O[0]); a2 = math.atan2(t2[1] - O[1], t2[0] - O[0])
    da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
    pts = [(O[0] + r * math.cos(a1 + da * i / n), O[1] + r * math.sin(a1 + da * i / n)) for i in range(n + 1)]
    return pts, t1, t2


def geometry(p):
    """Leaf face (with the corner cut away) and the flap, in leaf-local coordinates (origin at leaf centre)."""
    w, h, wv, tp = p["w"], p["h"], p["wave"], p["taper"]
    r1, r2, r3 = p["radii"]      # top-left, top-right, bottom-right (bottom-left is the turned corner)
    L, R, T, B = -w / 2, w / 2, -h / 2, h / 2
    TL, TR, BR = (L + tp / 2, T), (R - tp / 2, T), (R, B)
    K = (L, B)                   # the corner that is turned
    A = (L + p["a"], B)          # fold meets the bottom edge
    # fold meets the fore-edge (which may lean in towards the top)
    tc = p["c"] / h
    C = (K[0] + (TL[0] - K[0]) * tc, B - p["c"])
    corners = [(C, 0), (TL, r1), (TR, r2), (BR, r3), (A, 0)]
    waves = [(1.3, 0.17), (1.0, 0.61), (0.5, 0.39), (0.5, 0.83), (0, 0)]   # fore-edge most uneven, gutter nearly straight
    arcs = []
    for i, (V, r) in enumerate(corners):
        Vp = corners[i - 1][0]; Vn = corners[(i + 1) % len(corners)][0]
        arcs.append(fillet(V, Vp, Vn, r))
    face = []
    for i in range(len(corners)):
        pts, t1, t2 = arcs[i]
        face += pts
        if i < len(corners) - 1:
            nxt = arcs[i + 1][1]
            k, seed = waves[i]
            n = max(8, int(math.hypot(nxt[0] - t2[0], nxt[1] - t2[1]) / 8))
            face += wavy(t2, nxt, n, wv * k, seed)[1:]
    # the flap: the corner reflected across the fold, pulled back by `curl`
    fx, fy = C[0] - A[0], C[1] - A[1]
    fl = math.hypot(fx, fy)
    ux, uy = fx / fl, fy / fl
    t = (K[0] - A[0]) * ux + (K[1] - A[1]) * uy
    M = (A[0] + ux * t, A[1] + uy * t)               # foot of the corner on the fold
    Pf = (2 * M[0] - K[0], 2 * M[1] - K[1])          # where a flat crease would put the tip
    P = (M[0] + (Pf[0] - M[0]) * p["curl"], M[1] + (Pf[1] - M[1]) * p["curl"])
    nx, ny = (K[0] - M[0]), (K[1] - M[1])            # normal pointing out towards the corner
    nl = math.hypot(nx, ny); nx, ny = nx / nl, ny / nl
    return dict(face=face, A=A, C=C, M=M, P=P, n=(nx, ny), Pf=Pf)


def flap_path(g, p):
    A, C, P, (nx, ny) = g["A"], g["C"], g["P"], g["n"]
    roll, tr = p["roll"], p["tipr"]
    # base: from C to A, bulging out towards the corner (the rolled edge of the turn)
    mid = ((A[0] + C[0]) / 2 + nx * roll * 2, (A[1] + C[1]) / 2 + ny * roll * 2)

    def side(Q, bow):
        # edge from Q to the tip; bow > 0 bows outwards (away from the flap's centre), < 0 inwards
        cx_, cy_ = (Q[0] + P[0]) / 2, (Q[1] + P[1]) / 2
        dx, dy = P[0] - Q[0], P[1] - Q[1]
        L = math.hypot(dx, dy)
        px_, py_ = -dy / L, dx / L
        # choose the perpendicular that points away from the flap's centre
        gx, gy = (A[0] + C[0] + P[0]) / 3, (A[1] + C[1] + P[1]) / 3
        if (cx_ - gx) * px_ + (cy_ - gy) * py_ < 0:
            px_, py_ = -px_, -py_
        return (cx_ + px_ * L * bow, cy_ + py_ * L * bow)

    def toward(X, Y, d):
        dx, dy = Y[0] - X[0], Y[1] - X[1]
        L = math.hypot(dx, dy)
        return (Y[0] - dx / L * d, Y[1] - dy / L * d)

    qa, qc = side(A, p["bow_a"]), side(C, p["bow_c"])
    ea = toward(qa, P, tr)   # stop short of the tip on each side, then round it
    ec = toward(qc, P, tr)
    # the upper edge of the flap faces the light: that edge alone gets a thin highlight
    lit = f"M{C[0]:.1f},{C[1]:.1f} Q{qc[0]:.1f},{qc[1]:.1f} {ec[0]:.1f},{ec[1]:.1f} Q{P[0]:.1f},{P[1]:.1f} {ea[0]:.1f},{ea[1]:.1f}"
    return lit, (f"M{C[0]:.1f},{C[1]:.1f} Q{mid[0]:.1f},{mid[1]:.1f} {A[0]:.1f},{A[1]:.1f} "
            f"Q{qa[0]:.1f},{qa[1]:.1f} {ea[0]:.1f},{ea[1]:.1f} "
            f"Q{P[0]:.1f},{P[1]:.1f} {ec[0]:.1f},{ec[1]:.1f} "
            f"Q{qc[0]:.1f},{qc[1]:.1f} {C[0]:.1f},{C[1]:.1f} Z")


def build(p, name):
    g = geometry(p)
    face = fmt(g["face"])
    lit, flap = flap_path(g, p)
    M, P = g["M"], g["P"]
    nx, ny = g["n"]
    # gradient runs from the rolled fold to the tip
    g0 = (M[0] + nx * p["roll"] * 1.5, M[1] + ny * p["roll"] * 1.5)
    stops = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in zip(p["stops"], p["back"]))
    sx = -1 if p["mirror"] else 1
    tf = f'translate({p["cx"]} {p["cy"]}) rotate({p["rot"]}) scale({sx} 1)'
    ink = p["ink"]
    defs = (
        f'<linearGradient id="{name}-back" gradientUnits="userSpaceOnUse" x1="{g0[0]:.1f}" y1="{g0[1]:.1f}" x2="{P[0]:.1f}" y2="{P[1]:.1f}">{stops}</linearGradient>'
        f'<filter id="{name}-sh" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feDropShadow dx="0" dy="3" stdDeviation="2.5" flood-color="{ink}" flood-opacity="{p["contact"]}"/>'
        f'<feDropShadow dx="0" dy="12" stdDeviation="18" flood-color="{ink}" flood-opacity="{p["ambient"]}"/></filter>'
        f'<filter id="{name}-fs" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>'
        f'<clipPath id="{name}-fc"><path d="{face}"/></clipPath>'
        f'<clipPath id="{name}-lc"><path d="{flap}"/></clipPath>'
    )
    lw, lc, lo = p["lit"]
    # the flap's shadow on the face: light from above, so it falls a little below the flap
    inner = (
        f'<g transform="{tf}">'
        f'<g filter="url(#{name}-sh)"><path d="{face}" fill="{p["face"]}"/><path d="{flap}" fill="{p["back"][1]}"/></g>'
        f'<g clip-path="url(#{name}-fc)"><path d="{flap}" transform="translate({p['fs_dx']} {p['fs_dy']})" fill="{ink}" opacity="{p["flap_shadow"]}" filter="url(#{name}-fs)"/></g>'
        f'<path d="{flap}" fill="url(#{name}-back)"/>'
        + (f'<path d="{lit}" fill="none" stroke="{lc}" stroke-width="{lw}" stroke-linecap="round" opacity="{lo}" clip-path="url(#{name}-lc)"/>' if lw else "")
        + f'</g>'
    )
    pts = g["face"]
    ar = cxs = cys = 0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        k = x0 * y1 - x1 * y0
        ar += k; cxs += (x0 + x1) * k; cys += (y0 + y1) * k
    gx, gy = cxs / (3 * ar), cys / (3 * ar)
    xs = [x for x, _ in pts]; ys = [y for _, y in pts]
    print(f"{name}: face centroid offset ({gx * (-1 if p['mirror'] else 1):+.0f},{gy:+.0f}) bbox {max(xs)-min(xs):.0f}x{max(ys)-min(ys):.0f} "
          f"= {100*(max(ys)-min(ys))/824:.0f}% of tile height")
    svg = kit.tile(inner, defs)
    out = os.path.join(HERE, f"{name}.svg")
    open(out, "w").write(svg)
    return out


PARCH = dict(taper=14, radii=(34, 14, 26), wave=4.0)   # hand-cut: top a touch narrower, uneven corners

VARIANTS = {
    "v1": dict(PARCH, curl=0.74, cx=500, cy=508, tipr=12, bow_c=0.10,
               face="#E8D3A8", back=("#A0652F", "#C59458", "#D5AE72")),
    "v2": dict(PARCH, rot=-4, cx=500, cy=508, curl=0.76, tipr=12, bow_c=0.10, contact=0.36,
               face="#E0C48F", back=("#8E5628", "#B98648", "#CB9D5F"), lit=(5, "#EFDDB6", 0.9)),
    "v3": dict(PARCH, cx=506, cy=504, w=468, h=536, face="#DDBF88", a=196, c=226, curl=0.78, radii=(30, 18, 26), tipr=12,
               back=("#7A4614", "#A8743A", "#BC8E52"), lit=(5, "#E9D2A4", 0.9)),
}

NOTES = {
    "v1": "Upright folio, bottom-left corner curled over (the Hebrew turn); the back is the darker hair side.",
    "v2": "Tilted 4 degrees in an older, deeper parchment: reads as a page mid-turn.",
    "v3": "Wider, squarer leaf in a deeper parchment, with a smaller turn.",
}

if __name__ == "__main__":
    paths = []
    for k, v in VARIANTS.items():
        paths.append(build(dict(BASE, **v), k))
    kit.sheet(os.path.join(HERE, "sheet.png"), paths, list(VARIANTS), [NOTES[k] for k in VARIANTS])
    best = sys.argv[1] if len(sys.argv) > 1 else "v2"
    kit.render(os.path.join(HERE, f"{best}.svg"), os.path.join(HERE, "best-1024.png"), 1024)
    print("ok", paths)
