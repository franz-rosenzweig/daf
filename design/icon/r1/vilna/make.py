"""Daf icon, round 1, concept 2: "The Vilna page".

The layout of a printed Talmud page in solid blocks: the main text in the middle (with the big
opening word set apart at its head), Rashi on the inner side, Tosafot on the outer side, wrapping
around it. Parchment leaf with an feTurbulence grain, flat sepia ink, one soft contact shadow.

    python3 make.py            # writes v1.svg v2.svg v3.svg, sheet.png, best-1024.png
"""
import math, os, sys
sys.path.insert(0, "/srv/dev/daf/design/icon")
import kit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
P = "vilna"  # id prefix

PAL = dict(paper="#EAD7B0", paper_mid="#D9BA80", paper_deep="#BC8E52",
           sepia="#9A5B1F", deep="#7A4614", dark="#3A3127")


# ---------------------------------------------------------------- geometry helpers
def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def poly(*pts):
    return list(pts)


def clip_y(pts, y, keep_above):
    """Sutherland-Hodgman against a horizontal line (enough for these rectilinear shapes)."""
    inside = (lambda p: p[1] <= y) if keep_above else (lambda p: p[1] >= y)
    out = []
    for i in range(len(pts)):
        a, b = pts[i - 1], pts[i]
        if inside(b):
            if not inside(a):
                out.append((a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y))
            out.append(b)
        elif inside(a):
            out.append((a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y))
    return out


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


# ---------------------------------------------------------------- the page
def page(cfg):
    W, H = cfg["W"], cfg["H"]
    bow, lift = cfg.get("bow", 0), cfg.get("lift", 0)

    def curve(x, y):
        u = x / W
        return bow * 4 * u * (1 - u) + lift * u ** 2      # lift: the gutter side (right) bends away

    curve_fn = curve if (bow or lift) else None
    page_d = rounded(warp_pts(rect(0, 0, W, H), W, curve_fn), cfg.get("page_r", 7))

    ink = []
    for shape, tone in cfg["blocks"]:
        ink.append(f'<path d="{rounded(warp_pts(shape, W, curve_fn), cfg.get("ink_r", 4))}" fill="{cfg["tones"][tone]}"/>')

    g = cfg.get("grain", 0.22)
    mot = cfg.get("mottle", 0.14)
    sh = cfg.get("shadow", (12, 16, 0.24))
    dark = PAL["dark"]

    defs = (
        # one soft contact shadow, dropped from above
        f'<filter id="{P}-sh" x="-25%" y="-25%" width="150%" height="150%">'
        f'<feDropShadow dx="0" dy="{sh[0]}" stdDeviation="{sh[1]}" flood-color="{dark}" flood-opacity="{sh[2]}"/></filter>'
        # fine paper grain: dark specks
        f'<filter id="{P}-grain" x="0" y="0" width="100%" height="100%">'
        f'<feTurbulence type="fractalNoise" baseFrequency="{cfg.get("grain_f", 0.75)}" numOctaves="3" seed="11" result="n"/>'
        f'<feColorMatrix in="n" type="matrix" values="0 0 0 0 0.23  0 0 0 0 0.19  0 0 0 0 0.15  2.2 0 0 0 -0.95"/></filter>'
        # broad, faint mottle of the hide
        f'<filter id="{P}-mottle" x="0" y="0" width="100%" height="100%">'
        f'<feTurbulence type="fractalNoise" baseFrequency="0.011" numOctaves="2" seed="5" result="m"/>'
        f'<feColorMatrix in="m" type="matrix" values="0 0 0 0 0.74  0 0 0 0 0.56  0 0 0 0 0.32  2.4 0 0 0 -1.05"/></filter>'
        f'<clipPath id="{P}-clip"><path d="{page_d}"/></clipPath>'
    )

    pad = 40
    e = cfg.get("edge")                                # hairline that keeps the leaf's edge at small sizes
    edge = f'<path d="{page_d}" fill="none" stroke="{e[0]}" stroke-width="{e[1]}" stroke-opacity="{e[2]}"/>' if e else ""
    inner = (
        f'<g transform="translate({cfg["cx"]} {cfg["cy"]}) rotate({cfg.get("rot", 0)}) translate({-W / 2} {-H / 2})">'
        f'<path d="{page_d}" fill="{cfg["paper"]}" filter="url(#{P}-sh)"/>'
        f'<g clip-path="url(#{P}-clip)">'
        f'<rect x="{-pad}" y="{-pad}" width="{W + 2 * pad}" height="{H + 2 * pad + abs(bow) + abs(lift)}" filter="url(#{P}-mottle)" opacity="{mot}"/>'
        f'<g>{"".join(ink)}</g>'
        f'<rect x="{-pad}" y="{-pad}" width="{W + 2 * pad}" height="{H + 2 * pad + abs(bow) + abs(lift)}" filter="url(#{P}-grain)" opacity="{g}"/>'
        f'</g>{edge}</g>'
    )
    return kit.tile(inner, defs)


# ---------------------------------------------------------------- the layout, as parameters
def vilna(W=440, H=560, out=44, inn=44, top=50, bot=64, g=20, tw=66, rw=66, mB=320,
          word="drop", ww=64, wh=58, under="split", split=0.5, rstep=None, tstep=None,
          last=None, breaks=(), bg=14, head=False, notes=False):
    """Blocks of one amud. Outer side (Tosafot) on the left, the gutter (Rashi) on the right, as on
    an amud aleph; the main text's opening word sits top-right, where a Hebrew line starts.
    rstep/tstep = (y, dx): below y the main text pushes dx into Rashi's / Tosafot's column
    (negative dx: that commentary widens into the main text instead).
    last = (fraction, h): the main text's last line is short, leaving paper at its bottom-left."""
    x0, x1 = out, W - inn
    mL, mR = x0 + tw + g, x1 - rw - g
    yB = H - bot
    sx = x0 + (x1 - x0) * split                       # where Rashi and Tosafot meet under the main text
    ry, rdx = rstep or (None, 0)
    ty, tdx = tstep or (None, 0)
    B = []

    # main text
    m = [(mL, top)]
    if word == "drop":
        wx, wy = mR - ww, top + wh
        m += [(wx - g, top), (wx - g, wy + g), (mR, wy + g)]
        B.append((rect(wx, top, mR, wy), "word"))
    else:
        m += [(mR, top)]
    if ry:
        m += [(mR, ry), (mR + rdx, ry)]
    if last:
        nx = mR + rdx - (mR + rdx - mL + tdx) * last[0]
        m += [(mR + rdx, mB), (nx, mB), (nx, mB - last[1]), (mL - tdx, mB - last[1])]
    else:
        m += [(mR + rdx, mB), (mL - tdx, mB)]
    if ty:
        m += [(mL - tdx, ty), (mL, ty)]
    B.append((m, "main"))

    # Tosafot (outer) and Rashi (inner)
    tos = [(x0, top), (x0 + tw, top)]
    if ty:
        e = ty - g if tdx > 0 else ty + g
        tos += [(x0 + tw, e), (x0 + tw - tdx, e)]
    ras = [(x1, top), (x1 - rw, top)]
    if ry:
        e = ry - g if rdx > 0 else ry + g
        ras += [(x1 - rw, e), (x1 - rw + rdx, e)]
    if under == "split":
        tos += [(x0 + tw - tdx, mB + g), (sx - g / 2, mB + g), (sx - g / 2, yB), (x0, yB)]
        ras += [(x1 - rw + rdx, mB + g), (sx + g / 2, mB + g), (sx + g / 2, yB), (x1, yB)]
    elif under == "tosafot":
        tos += [(x0 + tw - tdx, mB + g), (x1, mB + g), (x1, yB), (x0, yB)]
        ras += [(x1 - rw + rdx, mB), (x1, mB)]
    else:
        tos += [(x0 + tw - tdx, yB), (x0, yB)]
        ras += [(x1 - rw + rdx, yB), (x1, yB)]
    # paragraph breaks: Tosafot's entries stand apart; Rashi's run on, with fewer breaks
    for col, pts in (("tos", tos), ("rashi", ras)):
        pieces = [pts]
        for c, y in sorted(breaks, key=lambda t: t[1]):
            if c == col:
                last_piece = pieces.pop()
                pieces += [clip_y(last_piece, y - bg / 2, True), clip_y(last_piece, y + bg / 2, False)]
        B += [(p, "comm") for p in pieces]

    if head:                                           # running head
        cx = (x0 + x1) / 2
        B.append((rect(cx - 56, top - 26, cx + 56, top - 14), "comm"))
    if notes:                                          # Ein Mishpat notes in the outer margin
        B.append((rect(out - 30, top + 4, out - 14, top + 70), "comm"))
        B.append((rect(out - 30, top + 90, out - 14, top + 130), "comm"))
    return dict(W=W, H=H, blocks=B)


def cfg(layout, cx=512, cy=500, rot=0, bow=0, paper=PAL["paper"], main=PAL["deep"], word=None,
        comm=PAL["paper_deep"], **kw):
    d = dict(layout, cx=cx, cy=cy, rot=rot, bow=bow, paper=paper,
             tones=dict(main=main, word=word or main, comm=comm))
    d.update(kw)
    return d


# ---------------------------------------------------------------- the three variations
COMM = "#C9A26A"   # commentary: parchment deep, a shade lighter, as small type reads lighter than large
EDGE = (PAL["paper_deep"], 3, 0.55)


def leaf(W, H, side, tw, rw, out, inn, mB, rot, bow, **tones):
    """A tilted leaf where one commentary runs straight down its column and the other turns under the
    main text. side="aleph": gutter (Rashi) on the right; "bet": gutter on the left."""
    g = 20
    x0, x1 = out, W - inn
    split = (tw + g / 2) / (x1 - x0) if side == "aleph" else (x1 - rw - g / 2 - x0) / (x1 - x0)
    return cfg(vilna(W=W, H=H, out=out, inn=inn, tw=tw, rw=rw, g=g, ww=66, wh=60, mB=mB, split=split),
               cy=498, rot=rot, bow=bow, ink_r=2.5, edge=EDGE, **tones)


def v1():
    """The leaf, picked up: a folio-shaped amud aleph tilted 3 degrees with a slight arch. Tosafot runs
    straight down the outer side, Rashi down the gutter side and under the main text. Four blocks."""
    return leaf(390, 536, "aleph", tw=56, rw=60, out=44, inn=36, mB=322, rot=-3, bow=-6,
                main=PAL["deep"], comm=PAL["paper_deep"])


def v2():
    """Upright, the full daf: both commentaries turn under the main text and meet off-centre; lighter
    commentary (small type reads lighter); the Ein Mishpat notes in the outer margin."""
    return cfg(vilna(W=410, H=552, out=52, inn=38, tw=66, rw=62, split=0.40, ww=64, wh=58, mB=316, notes=True),
               ink_r=2.5, main=PAL["deep"], comm=COMM, edge=EDGE)


def v3():
    """Amud bet, leaning the other way: gutter on the left, so Rashi wraps under from the left and
    Tosafot runs straight down the outer side; the opening word in Daf's blue, sepia main text."""
    return leaf(390, 536, "bet", tw=60, rw=56, out=36, inn=44, mB=322, rot=3, bow=-6,
                main=PAL["sepia"], word="#1A7DA4", comm=PAL["paper_deep"])


VARIANTS = [
    ("v1", v1, "The leaf picked up: Tosafot straight down the outer side, Rashi down the gutter and under. Four blocks."),
    ("v2", v2, "Upright, the full daf: both commentaries turn under and meet off-centre; margin notes; lighter commentary."),
    ("v3", v3, "Amud bet, leaning right: Rashi wraps from the left; the opening word in Daf's blue."),
]


def main(argv):
    paths = []
    for name, fn, _ in VARIANTS:
        p = os.path.join(HERE, f"{name}.svg")
        open(p, "w").write(page(fn()))
        paths.append(p)
    if "--no-render" in argv:
        return
    kit.sheet(os.path.join(HERE, "sheet.png"), paths, [v[0].upper() for v in VARIANTS], [v[2] for v in VARIANTS])
    best = os.environ.get("BEST", "v1")
    kit.render(os.path.join(HERE, f"{best}.svg"), os.path.join(HERE, "best-1024.png"), 1024)


if __name__ == "__main__":
    main(sys.argv[1:])
