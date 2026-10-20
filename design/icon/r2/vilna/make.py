"""Daf icon, round 2: "The Vilna page", six variations.

The layout of a printed Talmud page in solid blocks: the main text in the middle with its opening
word set apart at the top right (where a Hebrew line starts), Tosafot down the outer side, Rashi down
the gutter side and turning under the main text. Parchment leaf with an feTurbulence grain, flat
sepia ink, one soft contact shadow. Grown from round 1 (../../r1/vilna/make.py).

    python3 make.py            # writes v1..v6.svg, sheet.png, best-1024.png
"""
import math, os, sys
sys.path.insert(0, "/srv/dev/daf/design/icon")
import kit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
P = "vl"  # id prefix

PAL = dict(paper="#EAD7B0", paper_mid="#D9BA80", paper_deep="#BC8E52",
           sepia="#9A5B1F", deep="#7A4614", dark="#3A3127", blue="#1A7DA4")
EDGE = (PAL["paper_deep"], 3, 0.55)


# ---------------------------------------------------------------- geometry helpers
def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def mirror(pts, W):
    return [(W - x, y) for x, y in reversed(pts)]


def quad(p0, p1, p2, t):
    return ((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])


def reflect(p, a, b):
    """p reflected across the line through a and b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    fx, fy = a[0] + t * dx, a[1] + t * dy
    return (2 * fx - p[0], 2 * fy - p[1])


def warp_pts(pts, W, curve, steps=28):
    """Subdivide horizontal edges and push them by the page curve d(x); verticals stay straight."""
    if not curve:
        return pts
    out = []
    n = len(pts)
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        k = max(1, int(abs(x1 - x0) / W * steps)) if abs(y1 - y0) < 1e-6 else 1
        for j in range(k):
            t = j / k
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            out.append((x, y + curve(x, y)))
    return out


def rounded(pts, r):
    """Path through pts with corners (turns > 20 deg) rounded by r."""
    n = len(pts)
    d = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        a = (p1[0] - p0[0], p1[1] - p0[1]); b = (p2[0] - p1[0], p2[1] - p1[1])
        la, lb = math.hypot(*a), math.hypot(*b)
        if la < 1e-6 or lb < 1e-6:
            continue
        cos = (a[0] * b[0] + a[1] * b[1]) / (la * lb)
        if r <= 0 or cos > math.cos(math.radians(20)):
            d.append(("L", p1))
            continue
        rr = min(r, la / 2, lb / 2)
        s = (p1[0] - a[0] / la * rr, p1[1] - a[1] / la * rr)
        e = (p1[0] + b[0] / lb * rr, p1[1] + b[1] / lb * rr)
        d.append(("L", s)); d.append(("Q", p1, e))
    parts = []
    for k, item in enumerate(d):
        if item[0] == "L":
            parts.append(("M" if k == 0 else "L") + f"{item[1][0]:.1f},{item[1][1]:.1f}")
        else:
            parts.append(f"Q{item[1][0]:.1f},{item[1][1]:.1f} {item[2][0]:.1f},{item[2][1]:.1f}")
    return " ".join(parts) + " Z"


# ---------------------------------------------------------------- the layout
def vilna(W=448, H=544, out=32, inn=32, top=32, bot=64, g=32, tw=64, rw=64, mB=320,
          ww=64, wh=64, under="rashi", split=None, notes=False):
    """Blocks of one amud aleph: Tosafot (outer) on the left, Rashi (gutter) on the right.
    under = "rashi": Tosafot runs straight down, Rashi turns under the main text (the keyhole);
            "split": both turn under and meet at `split` (fraction of the text width)."""
    x0, x1 = out, W - inn
    mL, mR = x0 + tw + g, x1 - rw - g
    yB = H - bot
    wx, wy = mR - ww, top + wh
    B = [([(mL, top), (wx - g, top), (wx - g, wy + g), (mR, wy + g), (mR, mB), (mL, mB)], "main"),
         (rect(wx, top, mR, wy), "word")]
    if under == "rashi":
        B.append((rect(x0, top, x0 + tw, yB), "comm"))
        B.append(([(x1 - rw, top), (x1, top), (x1, yB), (x0 + tw + g, yB), (x0 + tw + g, mB + g), (x1 - rw, mB + g)], "comm"))
    else:
        sx = x0 + (x1 - x0) * split
        B.append(([(x0, top), (x0 + tw, top), (x0 + tw, mB + g), (sx - g / 2, mB + g), (sx - g / 2, yB), (x0, yB)], "comm"))
        B.append(([(x1 - rw, top), (x1, top), (x1, yB), (sx + g / 2, yB), (sx + g / 2, mB + g), (x1 - rw, mB + g)], "comm"))
    if notes:                                          # Ein Mishpat notes in the outer margin
        B.append((rect(out - 26, top + 4, out - 12, top + 64), "comm"))
        B.append((rect(out - 26, top + 84, out - 12, top + 120), "comm"))
    return B


# ---------------------------------------------------------------- line patterns (v4, large sizes)
def line_pattern(pid, color, period, weight, y0=0):
    """Horizontal type lines: `weight` of ink every `period` units, starting at y0."""
    return (f'<pattern id="{pid}" patternUnits="userSpaceOnUse" x="0" y="{y0}" width="64" height="{period}">'
            f'<rect x="0" y="0" width="64" height="{weight}" fill="{color}"/></pattern>')


# ---------------------------------------------------------------- one leaf
def shared_defs(sh=(12, 16, 0.24), grain_f=0.75):
    dark = PAL["dark"]
    return (
        f'<filter id="{P}-sh" x="-25%" y="-25%" width="150%" height="150%">'
        f'<feDropShadow dx="0" dy="{sh[0]}" stdDeviation="{sh[1]}" flood-color="{dark}" flood-opacity="{sh[2]}"/></filter>'
        f'<filter id="{P}-grain" x="0" y="0" width="100%" height="100%">'
        f'<feTurbulence type="fractalNoise" baseFrequency="{grain_f}" numOctaves="3" seed="11" result="n"/>'
        f'<feColorMatrix in="n" type="matrix" values="0 0 0 0 0.23  0 0 0 0 0.19  0 0 0 0 0.15  2.2 0 0 0 -0.95"/></filter>'
        f'<filter id="{P}-mottle" x="0" y="0" width="100%" height="100%">'
        f'<feTurbulence type="fractalNoise" baseFrequency="0.011" numOctaves="2" seed="5" result="m"/>'
        f'<feColorMatrix in="m" type="matrix" values="0 0 0 0 0.74  0 0 0 0 0.56  0 0 0 0 0.32  2.4 0 0 0 -1.05"/></filter>'
        f'<filter id="{P}-soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="7"/></filter>'
        # paper texture is for the large sizes; at 64 px and below it only reads as dirt
        f'<style>@media (max-width:64px){{.{P}-tex{{display:none}}}}</style>'
    )


def curve_of(c):
    W, bow = c["W"], c.get("bow", 0)
    lift, side = c.get("gutter_lift", (0, "right"))
    if not bow and not lift:
        return None

    def f(x, y):
        u = x / W if side == "right" else 1 - x / W
        return bow * 4 * (x / W) * (1 - x / W) + lift * u ** 3
    return f


def leaf(c, uid, shadow=True):
    """One parchment leaf, drawn in page-local coordinates and placed at (cx, cy) with rotation.
    Returns (svg, defs). Keys: W H cx cy rot bow paper blocks tones [lines] ink_r edge fold."""
    W, H = c["W"], c["H"]
    bow = c.get("bow", 0)
    curve = curve_of(c)
    outline = rect(0, 0, W, H)
    fold = c.get("fold")
    if fold:                                           # bottom-left corner lifting (the Hebrew turn)
        a, b = fold["a"], fold["b"]
        A, Bp, C = (0, H - a), (b, H), (0, H)
        M = ((A[0] + Bp[0]) / 2, (A[1] + Bp[1]) / 2)
        sQ = fold.get("bend", 0.22)                    # the crease bows toward the corner as the leaf bends
        Q = (M[0] + (C[0] - M[0]) * sQ, M[1] + (C[1] - M[1]) * sQ)
        crease = [quad(Bp, Q, A, t / 12) for t in range(13)]
        outline = [(0, 0), (W, 0), (W, H)] + crease
    page_d = rounded(warp_pts(outline, W, curve), c.get("page_r", 7))
    r = c.get("ink_r", 2.5)

    def ink(fills, cls=""):
        paths = "".join(f'<path d="{rounded(warp_pts(s, W, curve), r)}" fill="{fills[t]}"/>' for s, t in c["blocks"])
        return f'<g class="{cls}">{paths}</g>' if cls else paths

    defs = f'<clipPath id="{P}-clip{uid}"><path d="{page_d}"/></clipPath>'
    if c.get("lines"):                                 # size tiers, each its own drawing (see v4)
        defs += "".join(c["lines"]["defs"])
        body = "".join(ink(fills, f"{P}-{cls}") for cls, fills in c["lines"]["tiers"]) + ink(c["tones"], f"{P}-small")
    else:
        body = ink(c["tones"])

    pad = 40
    fx = f'x="{-pad}" y="{-pad}" width="{W + 2 * pad}" height="{H + 2 * pad + abs(bow) + abs(c.get("gutter_lift", (0,))[0])}"'
    e = c.get("edge")
    edge = f'<path d="{page_d}" fill="none" stroke="{e[0]}" stroke-width="{e[1]}" stroke-opacity="{e[2]}"/>' if e else ""
    flap = ""
    if fold:
        Cr = reflect(C, A, Bp)
        f = fold.get("reach", 0.8)                     # the tip is foreshortened as it lifts toward us
        T = (M[0] + (Cr[0] - M[0]) * f, M[1] + (Cr[1] - M[1]) * f)
        k = fold.get("curl", 0.12)

        def bend(p, q, s):
            mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
            nx, ny = -(q[1] - p[1]), q[0] - p[0]
            return (mx + nx * s, my + ny * s)
        c1, c2 = bend(A, T, -k), bend(T, Bp, -k)
        flap_d = (f"M{A[0]:.1f},{A[1]:.1f} Q{c1[0]:.1f},{c1[1]:.1f} {T[0]:.1f},{T[1]:.1f} "
                  f"Q{c2[0]:.1f},{c2[1]:.1f} {Bp[0]:.1f},{Bp[1]:.1f} Q{Q[0]:.1f},{Q[1]:.1f} {A[0]:.1f},{A[1]:.1f} Z")
        gx0, gy0 = M; gx1, gy1 = T
        defs += (f'<linearGradient id="{P}-back{uid}" gradientUnits="userSpaceOnUse" x1="{gx0:.1f}" y1="{gy0:.1f}" x2="{gx1:.1f}" y2="{gy1:.1f}">'
                 f'<stop offset="0" stop-color="{fold["back"][0]}"/><stop offset="1" stop-color="{fold["back"][1]}"/></linearGradient>')
        flap = (f'<path d="{flap_d}" fill="{PAL["dark"]}" opacity="{fold.get("shade", 0.28)}" filter="url(#{P}-soft)" transform="translate(6 10)"/>'
                f'<path d="{flap_d}" fill="url(#{P}-back{uid})"/>')
    svg = (
        f'<g transform="translate({c["cx"]} {c["cy"]}) rotate({c.get("rot", 0)}) translate({-W / 2} {-H / 2})">'
        f'<path d="{page_d}" fill="{c.get("paper", PAL["paper"])}"{f" filter=\"url(#{P}-sh)\"" if shadow else ""}/>'
        f'<g clip-path="url(#{P}-clip{uid})">'
        f'<rect class="{P}-tex" {fx} filter="url(#{P}-mottle)" opacity="{c.get("mottle", 0.14)}"/>'
        f'{body}'
        f'<rect class="{P}-tex" {fx} filter="url(#{P}-grain)" opacity="{c.get("grain", 0.22)}"/>'
        f'</g>{edge}{flap}</g>'
    )
    return svg, defs


def icon(c):
    svg, defs = leaf(c, "a")
    return kit.tile(svg, shared_defs() + defs + c.get("style", ""))


def tones(main=PAL["deep"], word=None, comm=PAL["paper_deep"]):
    return dict(main=main, word=word or main, comm=comm)


# ---------------------------------------------------------------- v1: refined, hinted to the 32 px grid
# Every edge sits on a multiple of 32 canvas units, so at 32 px each block edge lands on a pixel edge
# (and on a 2 px edge at 64). The leaf is 14 x 17 cells: margin 1 | Tosafot 2 | gap 1 | main 6 |
# gap 1 | Rashi 2 | margin 1; main text 9 rows, a 1-row gap, Rashi's turn 4 rows, bottom margin 2.
def base(**kw):
    d = dict(W=448, H=544, cx=512, cy=496, blocks=vilna(), tones=tones(PAL["deep"], comm="#CFAB72"),
             ink_r=2, edge=EDGE)
    d.update(kw)
    return d


def v1():
    return base()


# ---------------------------------------------------------------- v2: the daf with its corner turned
def v2():
    return base(fold=dict(a=170, b=150, back=("#A9773D", "#C99D60")))


# ---------------------------------------------------------------- v3: an open Gemara
def amud_bet(lay, W, word_right=True):
    """Mirror an amud aleph across the page so Rashi sits on the left (gutter) side. The opening
    word can stay top right, where a Hebrew line starts, or mirror with everything else."""
    out = [(mirror(s, W), t) for s, t in lay]
    if not word_right:
        return out
    main = [s for s, t in lay if t == "main"][0]
    word = [s for s, t in lay if t == "word"][0]
    shift = (W - max(x for x, _ in main)) - min(x for x, _ in main)
    out = [(s, t) for s, t in out if t not in ("main", "word")]
    return out + [([(x + shift, y) for x, y in main], "main"), ([(x + shift, y) for x, y in word], "word")]


def spread(W=264, H=372, mB=(226, 196), lift=0, word_right=True, main=PAL["deep"], comm="#CFAB72", cy=500, gap=2):
    """Two amudim across the gutter: amud bet on the right (read first), the next amud aleph on the
    left. Their Rashi columns meet at the gutter. mB = where each page's main text ends (left, right)."""
    kw = dict(out=22, inn=16, top=24, bot=36, g=18, tw=36, rw=36, ww=40, wh=40)
    L = vilna(W=W, H=H, mB=mB[0], **kw)
    R = amud_bet(vilna(W=W, H=H, mB=mB[1], **kw), W, word_right)
    base_c = dict(W=W, H=H, cy=cy, tones=tones(main, comm=comm), ink_r=2, edge=EDGE, page_r=5)
    # a gentle curve: each leaf dips toward the gutter
    left = dict(base_c, cx=512 - W / 2 - gap / 2, blocks=L, bow=0, gutter_lift=(lift, "right"))
    right = dict(base_c, cx=512 + W / 2 + gap / 2, blocks=R, bow=0, gutter_lift=(lift, "left"))
    sl, dl = leaf(left, "l", shadow=False)
    sr, dr = leaf(right, "r", shadow=False)
    sh = f'<g filter="url(#{P}-sh)">{shadow_shape(left)}{shadow_shape(right)}</g>'
    return kit.tile(sh + sl + sr, shared_defs() + dl + dr)


def shadow_shape(c):
    W, H = c["W"], c["H"]
    return (f'<path d="{rounded(warp_pts(rect(0, 0, W, H), W, curve_of(c)), c.get("page_r", 7))}" fill="{PAL["paper"]}" '
            f'transform="translate({c["cx"] - W / 2} {c["cy"] - H / 2})"/>')


def v3():
    # uneven main texts (short on the left amud, long on the right) so the pair never reads as two eyes
    return spread(mB=(166, 272), lift=4)


# ---------------------------------------------------------------- v4: type lines large, blocks small
def v4(fine=((16, 8), (8, 3.5)), coarse=((24, 13), (16, 7)), word=(32, 24)):
    """One SVG, three drawings, picked by a media query on the image's own size:
      384 px and up  fine type lines: main text 16-unit leading, 8 ink; commentary 8 / 3.5
      128 to 383 px  coarse lines:    main 24 / 13; commentary 16 / 7 (fine ones would grey out)
      96 px and down V1's solid blocks (64, 32, 16).
    The opening word is two heavy lines of big type. Every line starts on its block's top edge
    (y = 32) and every leading divides the grid, so the lines meet the notch and Rashi's turn cleanly."""
    c = base()
    d, comm = PAL["deep"], PAL["paper_deep"]
    pats = [line_pattern(f"{P}-fm", d, *fine[0], 32), line_pattern(f"{P}-fc", comm, *fine[1], 32),
            line_pattern(f"{P}-cm", d, *coarse[0], 32), line_pattern(f"{P}-cc", comm, *coarse[1], 32),
            line_pattern(f"{P}-w", d, *word, 32)]
    c["lines"] = dict(defs=pats, tiers=[
        ("big", dict(main=f"url(#{P}-fm)", word=f"url(#{P}-w)", comm=f"url(#{P}-fc)")),
        ("mid", dict(main=f"url(#{P}-cm)", word=f"url(#{P}-w)", comm=f"url(#{P}-cc)"))])
    c["style"] = (f'<style>.{P}-big,.{P}-mid,.{P}-small{{display:none}}'
                  f'@media (min-width:384px){{.{P}-big{{display:inline}}}}'
                  f'@media (min-width:97px) and (max-width:383px){{.{P}-mid{{display:inline}}}}'
                  f'@media (max-width:96px){{.{P}-small{{display:inline}}}}</style>')
    return icon(c)


# ---------------------------------------------------------------- v5: one accent
def v5():
    return base(tones=tones(PAL["deep"], word=PAL["blue"], comm="#CFAB72"))


# ---------------------------------------------------------------- v6: wildcard, the tile is the page
def bare(blocks, ox, oy, tones_, grain=0.22, uid="b"):
    """Blocks laid straight onto the white tile: the tile is the paper. Grain clipped to the ink."""
    paths = "".join(f'<path d="{rounded(s, 3)}" fill="{tones_[t]}"/>' for s, t in blocks)
    clip = "".join(f'<path d="{rounded(s, 3)}"/>' for s, _ in blocks)
    defs = shared_defs() + f'<clipPath id="{P}-ink{uid}">{clip}</clipPath>'
    inner = (f'<g transform="translate({ox} {oy})">{paths}'
             f'<g clip-path="url(#{P}-ink{uid})"><rect class="{P}-tex" x="-20" y="-20" width="600" height="620" '
             f'filter="url(#{P}-grain)" opacity="{grain}"/></g></g>')
    return kit.tile(inner, defs)


def v6(comm="#D2AE74", main=PAL["deep"], word=None):
    # 16 x 17 cells on the 32 grid: Tosafot 3 | gap 1 | main 8 | gap 1 | Rashi 3; main 10 rows,
    # gap 1, Rashi's turn 6 rows. Offset (256, 224) keeps every edge on a pixel at 32 px.
    lay = vilna(W=512, H=544, out=0, inn=0, top=0, bot=0, g=32, tw=96, rw=96, mB=320, ww=96, wh=96)
    return bare(lay, 256, 224, tones(main, word=word, comm=comm))


VARIANTS = [
    ("v1", lambda: icon(v1()), "V1 refined: every ink edge on the 32 px grid, 1 px gaps at 32; deep main text on light commentary, so the keyhole holds at 32."),
    ("v2", lambda: icon(v2()), "Corner turned: the bottom-left lifts the Hebrew way, showing the darker amud bet. The layout leads."),
    ("v3", v3, "Open Gemara: amud bet right, the next amud aleph left, Rashi columns meeting at the gutter; uneven mains so it never looks back at you."),
    ("v4", v4, "Type lines at 128 px and up (finer still from 384), main heavy and commentary fine; V1's solid blocks at 64 and below. One SVG, switched by size."),
    ("v5", lambda: icon(v5()), "One accent: the opening word in Daf's blue on V1. Red-brown (#9E2F1E) is one parameter away."),
    ("v6", v6, "Wildcard: no leaf. The tile is the paper, so the keyhole can be a third bigger; the boldest at 16."),
]


def main(argv):
    paths = []
    only = [a for a in argv if not a.startswith("--")]
    for name, fn, _ in VARIANTS:
        if only and name not in only:
            continue
        p = os.path.join(HERE, f"{name}.svg")
        open(p, "w").write(fn())
        paths.append(p)
    if "--no-render" in argv:
        return
    kit.sheet(os.path.join(HERE, "sheet.png"), paths,
              [n.upper() for n, _, _ in VARIANTS if not only or n in only],
              [t for n, _, t in VARIANTS if not only or n in only])
    best = os.environ.get("BEST", "v1")
    kit.render(os.path.join(HERE, f"{best}.svg"), os.path.join(HERE, "best-1024.png"), 1024)


if __name__ == "__main__":
    main(sys.argv[1:])
