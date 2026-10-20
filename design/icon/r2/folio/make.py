"""The folio, round 2: one parchment leaf with its corner turned over to show the back (amud bet).

    python3 make.py [best]     # writes v1..v6.svg, sheet.png, best-1024.png

Everything is built in leaf-local coordinates (origin at the leaf's centre, y down) as dense
polygons. A fold line splits the leaf. The face keeps one side; the other side is reflected over the
fold, foreshortened (`curl`), sheared (`bend`, which bows its edges) and rolled (`roll`) to make the
turned flap. Light comes from above. The only gradient is on the flap, and only when `flat` is off.
"""
import math, os, sys
sys.path.insert(0, "/srv/dev/daf/design/icon")
import kit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
P = "folio"

INK = "#3A3127"
BLUE = "#1A7DA4"

BASE = dict(
    w=420, h=556,              # leaf (portrait, about a Gemara folio)
    cx=500, cy=508, rot=-4,    # placement on the tile; the box sits low-left so the weight lands on the visual centre
    mirror=False,
    taper=14,                  # top edge a touch narrower: hand-cut, not office paper
    radii=(34, 14, 26, 20),    # corners TL, TR, BR, BL (uneven, like parchment)
    wave=4.0,                  # gentle unevenness of the edges, px
    fold=("corner", 270, 320), # ("corner", a, c): a along the bottom edge, c up the fore-edge; or ("line", (x1,y1), (x2,y2), ref)
    curl=0.76,                 # foreshortening of the turned part (1 = folded flat)
    bend=14.0,                 # shear that bows the flap's edges (px per 100 px of depth, squared)
    roll=12,                   # how far the rolled fold bulges past the cut
    face="#E0C48F",
    back=("#8E5628", "#B98648", "#CB9D5F"), stops=(0.0, 0.4, 1.0),
    flat=False,                # True: no gradient anywhere, the back is back[1]
    lit=(5, "#EFDDB6", 0.9),   # the one lit edge on the flap: width, colour, opacity (None for none)
    accent=None,               # (colour, width): a thin line along the turn
    shadows=True, contact=0.36, ambient=0.18,
    flap_shadow=0.30, fs=(6, 10, 9),   # the flap's shadow on the face: dx, dy, blur
    blocks=None,               # Gemara layout on the face: list of (polygon, tone)
    tones=None,                # tone name -> (colour, opacity) for blocks
    persp=None,                # (tilt in degrees, focal length): the leaf lying on a desk, seen from above at an angle
    stack=None,                # leaves under the top one: list of (dx, dy, drot, colour), bottom first
)


# ----------------------------------------------------------------- geometry
def wavy(p0, p1, amp, seed, step=8):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1
    n = max(6, int(L / step))
    nx, ny = -dy / L, dx / L
    out = []
    for i in range(n):
        t = i / n
        env = math.sin(math.pi * t) ** 2
        off = amp * env * (0.7 * math.sin(2 * math.pi * (0.9 * t + seed)) + 0.3 * math.sin(2 * math.pi * (1.7 * t + 2 * seed)))
        out.append((p0[0] + dx * t + nx * off, p0[1] + dy * t + ny * off))
    return out


def fillet(V, Vp, Vn, r, n=14):
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
    return [(O[0] + r * math.cos(a1 + da * i / n), O[1] + r * math.sin(a1 + da * i / n)) for i in range(n + 1)], t1, t2


def leaf(p):
    """The whole leaf outline, clockwise from the top-left corner."""
    w, h, tp, wv = p["w"], p["h"], p["taper"], p["wave"]
    L, R, T, B = -w / 2, w / 2, -h / 2, h / 2
    corners = [((L + tp / 2, T), p["radii"][0]), ((R - tp / 2, T), p["radii"][1]), ((R, B), p["radii"][2]), ((L, B), p["radii"][3])]
    waves = [(1.0, 0.61), (0.5, 0.39), (0.6, 0.83), (1.3, 0.17)]      # top, gutter (nearly straight), bottom, fore-edge (most uneven)
    arcs = [fillet(V, corners[i - 1][0], corners[(i + 1) % 4][0], r) for i, (V, r) in enumerate(corners)]
    pts = []
    for i in range(4):
        pts += arcs[i][0]
        k, seed = waves[i]
        pts += wavy(arcs[i][2], arcs[(i + 1) % 4][1], wv * k, seed)[1:]
    return pts


def clip_half(pts, side):
    """Sutherland-Hodgman: keep the part where side(pt) >= 0."""
    out = []
    n = len(pts)
    for i in range(n):
        a, b = pts[i - 1], pts[i]
        sa, sb = side(a), side(b)
        if sb >= 0:
            if sa < 0:
                t = sa / (sa - sb); out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            out.append(b)
        elif sa >= 0:
            t = sa / (sa - sb); out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def turn(p):
    """Face polygon, flap polygon (+ which flap points lie on the fold) and the gradient axis."""
    w, h = p["w"], p["h"]
    L, B = -w / 2, h / 2
    f = p["fold"]
    if f[0] == "corner":
        C, A, ref = (L, B - f[2]), (L + f[1], B), (L, B)
    else:
        C, A, ref = f[1], f[2], f[3]
    ux, uy = A[0] - C[0], A[1] - C[1]; ul = math.hypot(ux, uy); ux, uy = ux / ul, uy / ul
    nx, ny = -uy, ux                                     # normal; make it point to the turned side
    if (ref[0] - C[0]) * nx + (ref[1] - C[1]) * ny < 0:
        nx, ny = -nx, -ny
    dist = lambda q: (q[0] - C[0]) * nx + (q[1] - C[1]) * ny
    along = lambda q: (q[0] - C[0]) * ux + (q[1] - C[1]) * uy
    pts = leaf(p)
    face = clip_half(pts, lambda q: -dist(q))
    cut = clip_half(pts, dist)
    # densify the fold edge of the cut part so the roll can bulge
    dense = []
    for i in range(len(cut)):
        a, b = cut[i], cut[(i + 1) % len(cut)]
        dense.append(a)
        if abs(dist(a)) < 1e-6 and abs(dist(b)) < 1e-6:
            for k in range(1, 30):
                t = k / 30; dense.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    on = [abs(dist(q)) < 1e-6 for q in dense]
    s_on = [along(q) for q, o in zip(dense, on) if o]
    s0, s1 = min(s_on), max(s_on)
    curl, bend, roll = p["curl"], p["bend"], p["roll"]
    curl2 = p.get("curl2") or curl                       # curl at the fold's far end (a page turned by its bottom corner leads there)
    flap, dmax = [], 0
    for q in dense:
        d, s = dist(q), along(q)
        bump = math.sin(math.pi * min(1, max(0, (s - s0) / (s1 - s0)))) if s1 > s0 else 0
        tt = min(1, max(0, (s - s0) / (s1 - s0))) if s1 > s0 else 0
        d2 = (curl + (curl2 - curl) * tt) * d - roll * bump * math.exp(-d / 40)
        s2 = s + bend * (d / 100) ** 2
        flap.append((C[0] + ux * s2 - nx * d2, C[1] + uy * s2 - ny * d2))
        dmax = max(dmax, d2)
    mid = (C[0] + ux * (s0 + s1) / 2, C[1] + uy * (s0 + s1) / 2)
    g0 = (mid[0] + nx * roll, mid[1] + ny * roll)
    g1 = (mid[0] - nx * dmax, mid[1] - ny * dmax)
    return dict(face=face, flap=flap, on=on, g=(g0, g1), whole=pts)


def lit_runs(flap, on, rot, up=-0.35):
    """Runs of the flap's outline whose outward normal points up (towards the light)."""
    area = sum(flap[i - 1][0] * flap[i][1] - flap[i][0] * flap[i - 1][1] for i in range(len(flap)))
    sgn = 1 if area > 0 else -1
    t = math.radians(rot)
    runs, cur = [], []
    n = len(flap)
    for i in range(n):
        a, b = flap[i], flap[(i + 1) % n]
        if on[i] and on[(i + 1) % n]:
            ok = False
        else:
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy) or 1
            ox, oy = (dy / L, -dx / L) if sgn > 0 else (-dy / L, dx / L)
            oy_r = ox * math.sin(t) + oy * math.cos(t)
            ok = oy_r < up
        if ok:
            if not cur:
                cur = [a]
            cur.append(b)
        elif cur:
            runs.append(cur); cur = []
    if cur:
        runs.append(cur)
    return runs


def fmt(pts, close=True):
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + (" Z" if close else "")


# ----------------------------------------------------------------- drawing
def mapper(p):
    """Identity, or: rotate on the desk, then tilt the desk away and project (the far edge shrinks)."""
    if not p["persp"]:
        return lambda pts: pts
    phi, f = math.radians(p["persp"][0]), p["persp"][1]
    t = math.radians(p["rot"])
    k = p["persp"][2] if len(p["persp"]) > 2 else 1.0     # rescale so the leaf keeps its size on the tile

    def m(pts):
        out = []
        for x, y in pts:
            x, y = x * math.cos(t) - y * math.sin(t), x * math.sin(t) + y * math.cos(t)
            Y, Z = y * math.cos(phi), -y * math.sin(phi)
            s = f / (f + Z)
            out.append((k * x * s, k * Y * s))
        return out
    return m


def build(p, name, outdir=HERE):
    g = turn(p)
    mp = mapper(p)
    face, flap, whole = fmt(mp(g["face"])), fmt(mp(g["flap"])), fmt(mp(g["whole"]))
    (x1, y1), (x2, y2) = mp(list(g["g"]))
    sx = -1 if p["mirror"] else 1
    rot = 0 if p["persp"] else p["rot"]
    tf = f'translate({p["cx"]} {p["cy"]}) rotate({rot}) scale({sx} 1)'
    defs = (
        f'<linearGradient id="{P}-back" gradientUnits="userSpaceOnUse" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}">'
        + "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in zip(p["stops"], p["back"])) + '</linearGradient>'
        f'<filter id="{P}-sh" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feDropShadow dx="0" dy="3" stdDeviation="2.5" flood-color="{INK}" flood-opacity="{p["contact"]}"/>'
        f'<feDropShadow dx="0" dy="12" stdDeviation="18" flood-color="{INK}" flood-opacity="{p["ambient"]}"/></filter>'
        f'<filter id="{P}-sh1" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="{INK}" flood-opacity="{p["contact"] * 0.8}"/></filter>'
        f'<filter id="{P}-fs" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="{p["fs"][2]}"/></filter>'
        f'<clipPath id="{P}-fc"><path d="{face}"/></clipPath>'
        f'<clipPath id="{P}-lc"><path d="{flap}"/></clipPath>'
    )
    shf = f' filter="url(#{P}-sh)"' if p["shadows"] else ""
    out = [f'<g transform="{tf}">']
    # leaves underneath (daf yomi): bottom first
    under = []
    for i, (dx, dy, dr, col) in enumerate(p["stack"] or []):
        t = f'translate({dx} {dy}) rotate({dr})'
        under.append(t)
        out.append(f'<path d="{whole}" transform="{t}" fill="{col}"{shf if i == 0 else (" filter=\"url(#" + P + "-sh1)\"" if p["shadows"] else "")}/>')
    if under:
        defs += f'<clipPath id="{P}-uc"><path d="{whole}" transform="{under[-1]}"/></clipPath>'
    # the top leaf: face and flap share one drop shadow
    back_fill = p["back"][1] if p["flat"] else f"url(#{P}-back)"
    out.append(f'<g{shf}><path d="{face}" fill="{p["face"]}"/><path d="{flap}" fill="{p["back"][1]}"/></g>')
    if p["blocks"]:
        out.append(f'<g clip-path="url(#{P}-fc)">' + "".join(
            f'<path d="{fmt(mp(poly))}" fill="{p["tones"][k][0]}" opacity="{p["tones"][k][1]}" stroke="{p["tones"][k][0]}" stroke-width="5" stroke-linejoin="round" stroke-opacity="1"/>'
            for poly, k in p["blocks"]) + '</g>')
    if p["flap_shadow"]:
        sh = f'<path d="{flap}" transform="translate({p["fs"][0]} {p["fs"][1]})" fill="{INK}" opacity="{p["flap_shadow"]}" filter="url(#{P}-fs)"/>'
        out.append(f'<g clip-path="url(#{P}-fc)">{sh}</g>')
        if under:
            out.append(f'<g clip-path="url(#{P}-uc)"><g>{sh}</g></g>')
    out.append(f'<path d="{flap}" fill="{back_fill}"/>')
    if p["lit"]:
        lw, lc, lo = p["lit"]
        for run in lit_runs(g["flap"], g["on"], p["rot"] * sx):
            out.append(f'<path d="{fmt(run, False)}" fill="none" stroke="{lc}" stroke-width="{lw}" stroke-linecap="round" stroke-linejoin="round" opacity="{lo}" clip-path="url(#{P}-lc)"/>')
    if p["accent"]:
        col, aw = p["accent"]
        base = [q for q, o in zip(g["flap"], g["on"]) if o]
        out.append(f'<path d="{fmt(mp(base), False)}" fill="none" stroke="{col}" stroke-width="{aw}" stroke-linecap="round"/>')
    out.append('</g>')
    # report: fill of the tile and where the ink's weight sits
    xs = [q[0] for q in mp(g["whole"])]; ys = [q[1] for q in mp(g["whole"])]
    print(f"{name}: leaf {max(xs) - min(xs):.0f}x{max(ys) - min(ys):.0f}, {100 * (max(ys) - min(ys)) / 824:.0f}% of tile height")
    svg = kit.tile("".join(out), defs)
    path = os.path.join(outdir, f"{name}.svg")
    open(path, "w").write(svg)
    return path


# ----------------------------------------------------------------- the Gemara layout, as a whisper
def gemara(w, h, top=58, out=40, inn=36, bot=64, g=18, tw=54, rw=58, mfrac=0.52, word=(58, 50)):
    """Amud aleph in four quiet shapes: Tosafot down the outer (left) side, Rashi down the gutter (right)
    and under the main text, the main text with its opening word set apart at the top right (where a
    Hebrew line begins)."""
    L, T = -w / 2, -h / 2
    x0, x1 = L + out, w / 2 - inn
    yT, yB = T + top, h / 2 - bot
    mL, mR = x0 + tw + g, x1 - rw - g
    mB = yT + (yB - yT) * mfrac
    ww, wh = word
    wx = mR - ww
    return [
        ([(wx, yT), (mR, yT), (mR, yT + wh), (wx, yT + wh)], "word"),
        ([(mL, yT), (wx - g, yT), (wx - g, yT + wh + g), (mR, yT + wh + g), (mR, mB), (mL, mB)], "main"),
        ([(x0, yT), (x0 + tw, yT), (x0 + tw, yB), (x0, yB)], "comm"),
        ([(x1 - rw, yT), (x1, yT), (x1, yB), (mL, yB), (mL, mB + g), (x1 - rw, mB + g)], "comm"),
    ]


# ----------------------------------------------------------------- the six variations
def V(**kw):
    return dict(BASE, **kw)


VARIANTS = {
    # 1. v2 refined for the Dock: a bigger, deeper leaf, a bolder turn
    "v1": V(w=440, h=566, face="#DDBE86", back=("#7E4A1E", "#AE7B3E", "#C49455"), fold=("corner", 300, 350), curl=0.80,
            lit=(5, "#EDD8AC", 0.95), contact=0.40, ambient=0.22),
    # 2. the daf on its face, as a whisper; the turn leads
    "v2": V(face="#E6CFA0", blocks=gemara(420, 556, top=70, out=48, inn=44, bot=76, g=22, tw=48, rw=52, word=(50, 44)), tones=dict(word=("#9A5B1F", 0.15), main=("#9A5B1F", 0.13), comm=("#9A5B1F", 0.08)),
            back=("#8E5628", "#B98648", "#CB9D5F")),
    # 3. daf yomi: the next leaf waits underneath, the top one turning
    "v3": V(w=400, h=530, cx=496, cy=502, face="#E6CFA0", fold=("corner", 250, 300),
            stack=[(12, 12, 3.5, "#CBA86F"), (5, 6, 1.5, "#DABE8A")]),
    # 4. the turn as the hero: the whole fore-edge lifting, led by its bottom corner
    "v4": V(fold=("line", (-178, -278), (60, 278), (-210, 0)), curl=0.45, curl2=0.74, bend=-10, roll=18, cx=494,
            back=("#8E5628", "#B98648", "#D2A86A")),
    # 5. Moshe-flat: one tone, one tint, one thin accent
    "v5": V(flat=True, shadows=False, flap_shadow=0, lit=None, face="#E3C893", back=("#B4834A", "#C79A5E", "#C79A5E")),
    # 6. wildcard: only the corner. The leaf is bigger than the tile and runs off its top and right,
    #    so the turn is the whole icon and there is no "sheet of paper" left to read as a document
    "v6": V(w=760, h=980, cx=650, cy=300, rot=-4, radii=(34, 14, 26, 30), wave=6, fold=("corner", 330, 390), curl=0.80,
            face="#DDBE86", back=("#7E4A1E", "#AE7B3E", "#C49455"), lit=(6, "#EDD8AC", 0.95), contact=0.40, ambient=0.22),
}

NOTES = {
    "v1": "Round 1's v2 made louder: a bigger, deeper leaf and a bolder turn.",
    "v2": "The daf's layout in pale sepia on the face, as a whisper; the turn leads.",
    "v3": "Daf yomi: the next leaf waits underneath, and the top one is turning.",
    "v4": "The turn as the hero: half the leaf lifts to show its back.",
    "v5": "Moshe-flat: one tone and one tint, no shadow. Daf's blue was tried at the turn and didn't earn its place.",
    "v6": "Wildcard: only the corner. The leaf runs off the tile, so the turn is the whole icon.",
}

if __name__ == "__main__":
    only = [a for a in sys.argv[1:] if a in VARIANTS]
    paths = [build(v, k) for k, v in VARIANTS.items()]
    kit.sheet(os.path.join(HERE, "sheet.png"), paths, list(VARIANTS), [NOTES[k] for k in VARIANTS])
    best = only[0] if only else "v4"
    kit.render(os.path.join(HERE, f"{best}.svg"), os.path.join(HERE, "best-1024.png"), 1024)
    print("ok")
