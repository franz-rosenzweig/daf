#!/usr/bin/env python3
"""Daf icon, round 3: refining round 2's V2, the beech tree rooted in two closed books ("Tree D").

Small optical moves, each shown on its own against the reference, then combined:
calmer crown, visual-centre placement, books with more character, deeper parchment and a firmer
trunk, and one accent spine (Daf's blue or a deep red-brown). Also a small drawing for 16-48 px.

    python3 make.py          # v2..final svgs, sheet.png, small.png, final.svg, final-small.svg

Every part is drawn with cubic Beziers. The grain (feTurbulence) and one lit edge
(feSpecularLighting, light from above) sit on the whole object, and there is one soft contact shadow.
"""
import math
import os
import sys

sys.path.insert(0, "/srv/dev/daf/design/icon")
import kit  # noqa: E402
import time  # noqa: E402


class _PatientTime:
    """kit waits 1.2 s for a page to paint; six filtered SVGs at four sizes need longer. Patched here, not in kit.py."""
    def __getattr__(self, k):
        return getattr(time, k)

    @staticmethod
    def sleep(s):
        time.sleep(s * 5)


kit.time = _PatientTime()

HERE = os.path.dirname(os.path.abspath(__file__))
ID = "tree"


# ---------------------------------------------------------------- geometry helpers (from r1/leaf)

def fmt(v):
    return f"{v:.1f}".rstrip("0").rstrip(".") if abs(v) > 1e-9 else "0"


def pt(p):
    # whole pixels on the 1024 grid keep the SVGs small enough for kit.sheet's single data URL
    return f"{round(p[0])},{round(p[1])}"


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def cubic(seg, t):
    p0, c1, c2, p1 = seg
    u = 1 - t
    return (u ** 3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t ** 3 * p1[0],
            u ** 3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t ** 3 * p1[1])


def sample(segs, n=60):
    out = []
    for i, s in enumerate(segs):
        for k in range(n + 1):
            if k == 0 and i > 0:
                continue
            out.append(cubic(s, k / n))
    return out


def segs_d(segs, move=True):
    """Path data for a chain of cubic segments."""
    d = f"M{pt(segs[0][0])}" if move else ""
    for _, c1, c2, p1 in segs:
        d += f" C{pt(c1)} {pt(c2)} {pt(p1)}"
    return d


def reverse(segs):
    return [(p1, c2, c1, p0) for p0, c1, c2, p1 in reversed(segs)]


def catmull(points, tension=1.0):
    """An open Catmull-Rom spline through `points`, as cubic Bezier segments."""
    segs = []
    n = len(points)
    for i in range(n - 1):
        p0 = points[max(i - 1, 0)]
        p1, p2 = points[i], points[i + 1]
        p3 = points[min(i + 2, n - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6 * tension, p1[1] + (p2[1] - p0[1]) / 6 * tension)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6 * tension, p2[1] - (p3[1] - p1[1]) / 6 * tension)
        segs.append((p1, c1, c2, p2))
    return segs


def ray_hit(origin, d, poly):
    """Distance along ray origin + t*d to the first crossing of polyline `poly`."""
    best = None
    ox, oy = origin
    dx, dy = d
    for (ax, ay), (bx, by) in zip(poly, poly[1:]):
        ex, ey = bx - ax, by - ay
        den = dx * ey - dy * ex
        if abs(den) < 1e-9:
            continue
        t = ((ax - ox) * ey - (ay - oy) * ex) / den
        u = ((ax - ox) * dy - (ay - oy) * dx) / den
        if t > 1e-6 and 0 <= u <= 1 and (best is None or t < best):
            best = t
    return best


def wavy(segs, amp, period, phase=0.0, side=1, keep=0.06):
    """Resample a margin and give it a slight natural undulation (teeth at the vein ends)."""
    pts = sample(segs, 80)
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + math.dist(a, b))
    total = acc[-1]
    step = period / 4
    out = []
    k = 0
    target = 0.0
    while target <= total:
        while k < len(acc) - 2 and acc[k + 1] < target:
            k += 1
        t = (target - acc[k]) / max(acc[k + 1] - acc[k], 1e-9)
        p = lerp(pts[k], pts[k + 1], t)
        tg = (pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])
        ln = math.hypot(*tg) or 1
        nrm = (tg[1] / ln * side, -tg[0] / ln * side)
        f = target / total
        env = min(1, f / keep) * min(1, (1 - f) / keep)   # calm at base and tip
        off = amp * env * math.sin(2 * math.pi * target / period + phase)
        out.append((p[0] + nrm[0] * off, p[1] + nrm[1] * off))
        target += step
    if math.dist(out[-1], pts[-1]) > 1:
        out.append(pts[-1])
    out[0], out[-1] = pts[0], pts[-1]
    return catmull(out)


def halfplane(q, ang, keep_sign, R=3000):
    """A big polygon covering one side of the line through q at angle `ang` (degrees)."""
    d = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
    n = (-d[1] * keep_sign, d[0] * keep_sign)
    a = (q[0] - d[0] * R, q[1] - d[1] * R)
    b = (q[0] + d[0] * R, q[1] + d[1] * R)
    c = (b[0] + n[0] * R, b[1] + n[1] * R)
    e = (a[0] + n[0] * R, a[1] + n[1] * R)
    return f"M{pt(a)} L{pt(b)} L{pt(c)} L{pt(e)} Z"


def reflect_matrix(q, ang):
    d = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
    r00, r01 = d[0] ** 2 - d[1] ** 2, 2 * d[0] * d[1]
    r10, r11 = r01, d[1] ** 2 - d[0] ** 2
    e = q[0] - (r00 * q[0] + r01 * q[1])
    f = q[1] - (r10 * q[0] + r11 * q[1])
    return f"matrix({r00:.5f} {r10:.5f} {r01:.5f} {r11:.5f} {e:.2f} {f:.2f})"


def rot(p, a, o=(0, 0)):
    """p rotated by `a` degrees clockwise (screen coordinates) about o."""
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    x, y = p[0] - o[0], p[1] - o[1]
    return (o[0] + c * x - s * y, o[1] + s * x + c * y)


def kappa_arc(c, r, a0, a1):
    """A circular arc as one cubic (|a1 - a0| <= 90 degrees), angles in degrees, screen coordinates."""
    t0, t1 = math.radians(a0), math.radians(a1)
    k = 4 / 3 * math.tan((t1 - t0) / 4)
    p0 = (c[0] + r * math.cos(t0), c[1] + r * math.sin(t0))
    p1 = (c[0] + r * math.cos(t1), c[1] + r * math.sin(t1))
    c1 = (p0[0] - k * r * math.sin(t0), p0[1] + k * r * math.cos(t0))
    c2 = (p1[0] + k * r * math.sin(t1), p1[1] - k * r * math.cos(t1))
    return (p0, c1, c2, p1)


# ---------------------------------------------------------------- palette: three families

C = dict(
    page="#F3E8CF",        # light parchment: pages, the underside of a turned-down leaf tip
    page_edge="#E2CDA1",   # the page block seen edge-on
    page_line="#C9AD7A",   # hairlines between pages
    leaf_lit="#E4C78F",    # mid parchment: a dry beech leaf, lit half
    leaf_shade="#CFA465",  # and its shaded half
    fold="#D7BC88",
    ink="#8E5726",         # ink: stems, roots, covers, lines of text
    ink_deep="#6F4217",
    cover="#A9733A",       # leather, between parchment and ink, so a dark stem still shows against it
)


class Scene:
    """Collects defs (clip paths, filters, gradients) with unique ids while parts are drawn."""

    def __init__(self):
        self.defs = []
        self.n = 0

    def uid(self, s):
        self.n += 1
        return f"{ID}-{s}{self.n}"


# ---------------------------------------------------------------- the beech leaf (round 1's signature)

BEECH = dict(w=(0.29, 0.27), p=(0.45, 0.46), base=((0.62, 0.0), (0.56, 0.01)), ka=(0.62, 0.62), kb=(0.42, 0.42),
             tip=((0.08, 0.22), (0.07, 0.24)))
LENS = [0.84, 0.86, 0.83, 0.87, 0.85, 0.58, 0.84, 0.80, 0.62, 0.86, 0.82]


def midrib(L, bow):
    return [((0, 0), (bow, -L / 3), (bow * 0.9, -2 * L / 3), (0, -L))]


def half_outline(L, h, side):
    w, p = h["w"], h["p"]
    bx, by = h["base"]
    ka, kb = h["ka"], h["kb"]
    tx, ty = h["tip"]
    s = side
    W = (s * w, -p * L)
    a = ((0, 0), (s * w * bx, -L * by), (s * w, -p * L + p * L * ka), W)
    b = (W, (s * w, -p * L - (1 - p) * L * kb), (s * w * tx, -L + L * ty), (0, -L))
    return [a, b]


def taper_path(pts, w0, w1, cap_end=True, cap_start=False, power=0.9):
    """A filled, tapered band along the polyline `pts` (already smooth and dense)."""
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + math.dist(a, b))
    tot = acc[-1] or 1
    left, right = [], []
    for i, p in enumerate(pts):
        q = pts[min(i + 1, len(pts) - 1)]
        r = pts[max(i - 1, 0)]
        tg = (q[0] - r[0], q[1] - r[1])
        ln = math.hypot(*tg) or 1
        n = (-tg[1] / ln, tg[0] / ln)
        w = (w0 + (w1 - w0) * (acc[i] / tot) ** power) / 2
        left.append((p[0] + n[0] * w, p[1] + n[1] * w))
        right.append((p[0] - n[0] * w, p[1] - n[1] * w))

    def cap(a, b, tip_dir, w):
        k = 0.55 * w
        return f" C{pt((a[0] + tip_dir[0] * k * 1.3, a[1] + tip_dir[1] * k * 1.3))} {pt((b[0] + tip_dir[0] * k * 1.3, b[1] + tip_dir[1] * k * 1.3))} {pt(b)}"

    e = (pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
    el = math.hypot(*e) or 1
    e = (e[0] / el, e[1] / el)
    s = (pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])
    sl = math.hypot(*s) or 1
    s = (s[0] / sl, s[1] / sl)
    d = segs_d(catmull(left))
    d += cap(left[-1], right[-1], e, w1) if cap_end else f" L{pt(right[-1])}"
    d += segs_d(reverse(catmull(right)), move=False)
    d += (cap(right[0], left[0], s, w0) if cap_start else "") + " Z"
    return d


def stem(points, w0, w1, color=None, cap_start=False, tension=1.0, power=0.9, density=5):
    """A tapered stem through `points` (a smooth Catmull-Rom line), w0 wide at the start, w1 at the end."""
    pts = sample(catmull(points, tension), density)
    return f'<path d="{taper_path(pts, w0, w1, cap_start=cap_start, power=power)}" fill="{color or C["ink"]}"/>'


def leaf(sc, at, L, angle, veins="natural", n=None, fold=None, petiole=0.0, bow=0.012, shape=BEECH,
         line_op=0.5, gutter=0.45, lit=None, shade=None, flip_light=None, rib=1.0):
    """One dry beech leaf. Its petiole starts at `at`; `angle` is where the tip points
    (degrees, 0 = straight up, clockwise positive). The half facing up is the lit one."""
    lit, shade = lit or C["leaf_lit"], shade or C["leaf_shade"]
    left_lit = (angle >= 0) if flip_light is None else flip_light
    margins = {}
    for i, (side, key) in enumerate(((-1, "left"), (1, "right"))):
        h = dict(w=shape["w"][i] * L, p=shape["p"][i], base=shape["base"][i], ka=shape["ka"][i],
                 kb=shape["kb"][i], tip=shape["tip"][i])
        segs = half_outline(L, h, side)
        if L >= 200:   # the slight wave of a beech margin only shows on big leaves
            segs = wavy(segs, L * 0.0035, L * 0.1, 0.9 if side > 0 else 0, side=-side)
        margins[key] = segs
    rib_w = rib
    rib = midrib(L, bow * L)
    halves = {k: segs_d(margins[k]) + segs_d(reverse(rib), move=False) + " Z" for k in margins}
    sil = segs_d(margins["left"]) + segs_d(reverse(margins["right"]), move=False) + " Z"

    # midrib: tapered from the base to the tip
    mw0, mw1 = max(L * 0.024 * rib_w, 2.6), max(L * 0.006, 1.0)
    rib_d = taper_path(sample(rib, 8), mw0, mw1, cap_end=False, power=0.8)

    # veins, or lines of text running out from the midrib
    vein_d = ""
    if veins:
        style = dict(natural=dict(angle=22, fan=10, kick=0.0), text=dict(angle=6, fan=6, kick=0.10),
                     branches=dict(angle=38, fan=14, kick=0.12))[veins]
        tapered = []
        n = n or max(4, round(L / 55))
        top = 0.72 if fold else 0.80
        paths = []
        for si, (side, key) in enumerate(((-1, "left"), (1, "right"))):
            poly = sample(margins[key], 40)
            for i in range(n):
                f = 0.13 + (top - 0.13) * i / max(n - 1, 1) + ((0.5 * (top - 0.13) / max(n - 1, 1) if veins == "branches" else 0.015) if side > 0 else 0)
                o = cubic(rib[0], f)
                o = (o[0] + side * max(L * 0.018, 2), o[1])
                a = math.radians(style["angle"] + style["fan"] * (i / max(n - 1, 1) - 0.5))
                d = (side * math.cos(a), -math.sin(a))
                hit = ray_hit(o, d, poly)
                if hit is None:
                    continue
                ln = hit * LENS[(i + 3 * si) % len(LENS)]
                e = (o[0] + d[0] * ln, o[1] + d[1] * ln)
                c1 = (o[0] + d[0] * ln * 0.35, o[1] + d[1] * ln * 0.35 - style["kick"] * ln)
                c2 = (o[0] + d[0] * ln * 0.7, o[1] + d[1] * ln * 0.7)
                paths.append(f"M{pt(o)} C{pt(c1)} {pt(c2)} {pt(e)}")
                if veins == "branches":
                    tapered.append(taper_path(sample([(o, c1, c2, e)], 8), L * 0.022 * (1 - 0.5 * f), L * 0.005, power=0.7))
        vw = max(L * 0.011, 1.6)
        if veins == "branches":
            vein_d = f'<path d="{" ".join(tapered)}" fill="{C["ink_deep"]}" fill-opacity="{line_op}"/>'
        else:
            vein_d = (f'<path d="{" ".join(paths)}" fill="none" stroke="{C["ink"]}" stroke-width="{vw:.2f}" '
                      f'stroke-linecap="round" stroke-opacity="{line_op}"/>')

    bid, gid = sc.uid("blade"), sc.uid("soft")
    sc.defs.append(f'<clipPath id="{bid}"><path d="{sil}"/></clipPath>'
                   f'<filter id="{gid}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="{L * 0.05:.1f}"/></filter>')
    blade = (f'<path d="{halves["left"]}" fill="{lit if left_lit else shade}"/>'
             f'<path d="{halves["right"]}" fill="{shade if left_lit else lit}"/>'
             f'<g clip-path="url(#{bid})"><path d="{segs_d(rib)}" fill="none" stroke="{C["ink"]}" stroke-width="{L * 0.16:.1f}" '
             f'stroke-opacity="{gutter * 0.35:.2f}" filter="url(#{gid})"/></g>'
             f'{vein_d}' + (f'<path d="{rib_d}" fill="{C["ink_deep"] if rib_w > 1 else C["ink"]}"/>' if rib_w > 0 else ""))

    flap = ""
    if fold:
        q, ang = (0, -fold[0] * L), fold[1]
        R = reflect_matrix(q, ang)
        body, cut, grad, fsh = sc.uid("body"), sc.uid("cut"), sc.uid("flapg"), sc.uid("flapsh")
        sdy = max(L * 0.022, 2)
        ldx, ldy = sdy * math.sin(math.radians(angle)), sdy * math.cos(math.radians(angle))
        sc.defs.append(
            f'<clipPath id="{body}"><path d="{halfplane(q, ang, 1)}"/></clipPath>'
            f'<clipPath id="{cut}"><path d="{halfplane(q, ang, -1)}"/></clipPath>'
            f'<linearGradient id="{grad}" gradientUnits="userSpaceOnUse" x1="{fmt(q[0])}" y1="{fmt(q[1])}" x2="0" y2="{fmt(-L)}">'
            f'<stop offset="0" stop-color="{C["fold"]}"/><stop offset="0.55" stop-color="{C["page"]}"/></linearGradient>'
            f'<filter id="{fsh}" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur in="SourceAlpha" stdDeviation="{L * 0.02:.1f}"/>'
            f'<feOffset dx="{ldx:.1f}" dy="{ldy:.1f}" result="b"/><feFlood flood-color="#6B4A22" flood-opacity="0.34"/>'
            f'<feComposite in2="b" operator="in"/></filter>')
        shape_ = f'<g transform="{R}"><path d="{sil}" clip-path="url(#{cut})"/></g>'
        blade = (f'<g clip-path="url(#{body})">{blade}</g>'
                 f'<g clip-path="url(#{bid})"><g clip-path="url(#{body})"><g filter="url(#{fsh})">{shape_}</g></g></g>')
        flap = f'<g transform="{R}"><path d="{sil}" clip-path="url(#{cut})" fill="url(#{grad})"/></g>'

    pet = ""
    if petiole:
        pet = stem([(0, 0), (L * 0.01, -petiole * 0.5), (0, -petiole - mw0)], max(L * 0.03, 3), mw0)
    return (f'<g transform="translate({at[0]:.1f} {at[1]:.1f}) rotate({angle:.1f})">{pet}'
            f'<g transform="translate(0 {-petiole:.1f})">{blade}{flap}</g></g>')


def spray(sc, points, w0, w1, leaves, color=None, **kw):
    """A twig through `points` with leaves alternating along it, as on a beech spray.
    `leaves` = [(t along the twig 0..1, angle off the twig in degrees (+ right, - left), length)]."""
    pts = sample(catmull(points), 8)
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + math.dist(a, b))
    out = []
    for t, off, L in leaves:
        target = t * acc[-1]
        i = max(1, min(len(pts) - 1, next((k for k, v in enumerate(acc) if v >= target), len(pts) - 1)))
        p, q = pts[i - 1], pts[i]
        f = (target - acc[i - 1]) / max(acc[i] - acc[i - 1], 1e-9)
        at = lerp(p, q, min(max(f, 0), 1))
        a = math.degrees(math.atan2(q[0] - p[0], -(q[1] - p[1])))
        out.append(leaf(sc, at, L, a + off, petiole=max(L * 0.05, 5), **kw))
    return stem(points, w0, w1, color or C["ink_deep"]) + "".join(out)


# ---------------------------------------------------------------- books

def open_book(sc, cx, top, W, H, dip, thick=18, cover=11, hump=0.55, lines=0, line_op=0.32, line_w=5.0,
              ragged=(0.86, 0.80, 0.88, 0.62, 0.84, 0.86, 0.70, 0.83)):
    """An open book from the front and a little above. `top` is the height of the outer top corners,
    `dip` how far the pages sink into the gutter. Returns (svg, info) with the gutter points."""

    def edges(s, dy=0.0, out=0.0):
        Gt = (cx, top + dip + dy)
        Ot = (cx + s * (W / 2 + out), top + dy)
        Ob = (cx + s * (W / 2 + out), top + H + dy)
        Gb = (cx, top + H + dip + dy)
        topE = (Gt, (cx + s * W * 0.05, top - hump * dip + dy), (cx + s * W * 0.27, top - hump * dip * 0.9 + dy), Ot)
        botE = (Gb, (cx + s * W * 0.05, top + H - hump * dip + dy), (cx + s * W * 0.27, top + H - hump * dip * 0.9 + dy), Ob)
        return topE, botE

    def page_d(s, dy=0.0, out=0.0):
        topE, botE = edges(s, dy, out)
        return segs_d([topE]) + f" L{pt(botE[3])}" + segs_d([(botE[3], botE[2], botE[1], botE[0])], move=False) + " Z"

    parts = []
    for s in (-1, 1):   # cover, then the page block, then the top page
        parts.append(f'<path d="{page_d(s, thick + cover, 9)}" fill="{C["cover"]}"/>')
    for s in (-1, 1):
        parts.append(f'<path d="{page_d(s, thick, 3)}" fill="{C["page_edge"]}"/>')
        for k in (0.36, 0.7):
            _, botE = edges(s, thick * k, 3 * k)
            parts.append(f'<path d="{segs_d([botE])}" fill="none" stroke="{C["page_line"]}" stroke-width="2.2"/>')
    for s in (-1, 1):
        g = sc.uid("gut")
        sc.defs.append(f'<linearGradient id="{g}" gradientUnits="userSpaceOnUse" x1="{cx:.1f}" y1="0" x2="{cx + s * W * 0.2:.1f}" y2="0">'
                       f'<stop offset="0" stop-color="{C["page_edge"]}"/><stop offset="1" stop-color="{C["page"]}"/></linearGradient>')
        parts.append(f'<path d="{page_d(s)}" fill="url(#{g})"/>')
    # lines of text following the curve of the page
    tl = []
    if lines:
        for s in (-1, 1):
            topE, botE = edges(s)
            for i in range(lines):
                u = 0.2 + 0.62 * i / max(lines - 1, 1)
                seg = tuple(lerp(topE[j], botE[j], u) for j in range(4))
                t1 = ragged[(i + (3 if s > 0 else 0)) % len(ragged)]
                pts = [cubic(seg, 0.1 + (t1 - 0.1) * k / 10) for k in range(11)]
                tl.append(segs_d(catmull(pts)))
        parts.append(f'<path d="{" ".join(tl)}" fill="none" stroke="{C["ink"]}" stroke-width="{line_w}" stroke-linecap="round" stroke-opacity="{line_op}"/>')
    info = dict(gutter_top=(cx, top + dip), gutter_bottom=(cx, top + H + dip), bottom=top + H + dip + thick + cover,
                edges=edges)
    return "".join(parts), info


def closed_book(x0, y0, W, T, cover=12, spine="left", lines=2, fore=8, spine_col=None):
    """A closed book lying flat, seen square from the front: the covers above and below,
    the page block between, the spine rounded on one side."""
    r = T / 2
    x1 = x0 + W
    rr = 6
    if spine == "left":
        d = (f"M{pt((x0 + r, y0))} L{pt((x1 - rr, y0))} C{pt((x1 - rr * 0.45, y0))} {pt((x1, y0 + rr * 0.45))} {pt((x1, y0 + rr))}"
             f" L{pt((x1, y0 + T - rr))} C{pt((x1, y0 + T - rr * 0.45))} {pt((x1 - rr * 0.45, y0 + T))} {pt((x1 - rr, y0 + T))}"
             f" L{pt((x0 + r, y0 + T))}" + segs_d([kappa_arc((x0 + r, y0 + r), r, 90, 180), kappa_arc((x0 + r, y0 + r), r, 180, 270)], move=False) + " Z")
        px0, px1 = x0 + r * 0.55, x1 - fore
    else:
        d = (f"M{pt((x1 - r, y0))} L{pt((x0 + rr, y0))} C{pt((x0 + rr * 0.45, y0))} {pt((x0, y0 + rr * 0.45))} {pt((x0, y0 + rr))}"
             f" L{pt((x0, y0 + T - rr))} C{pt((x0, y0 + T - rr * 0.45))} {pt((x0 + rr * 0.45, y0 + T))} {pt((x0 + rr, y0 + T))}"
             f" L{pt((x1 - r, y0 + T))}" + segs_d([kappa_arc((x1 - r, y0 + r), r, 90, 0), kappa_arc((x1 - r, y0 + r), r, 0, -90)], move=False) + " Z")
        px0, px1 = x0 + fore, x1 - r * 0.55
    py0, py1 = y0 + cover, y0 + T - cover
    pr = 3
    pages = (f"M{pt((px0, py0))} L{pt((px1 - pr, py0))} Q{pt((px1, py0))} {pt((px1, py0 + pr))} L{pt((px1, py1 - pr))}"
             f" Q{pt((px1, py1))} {pt((px1 - pr, py1))} L{pt((px0, py1))} Z")
    ls = "".join(f'<path d="M{pt((px0 + 4, py0 + (py1 - py0) * (k + 1) / (lines + 1)))} L{pt((px1 - 4, py0 + (py1 - py0) * (k + 1) / (lines + 1)))}" '
                 f'stroke="{C["page_line"]}" stroke-width="2.2" stroke-linecap="round"/>' for k in range(lines))
    cap = ""
    if spine_col:   # quarter binding: the spine, and a little of the boards, in their own leather
        ext = r * 0.45
        if spine == "left":
            cap = (f"M{pt((x0 + r + ext, y0 + T))} L{pt((x0 + r, y0 + T))}"
                   + segs_d([kappa_arc((x0 + r, y0 + r), r, 90, 180), kappa_arc((x0 + r, y0 + r), r, 180, 270)], move=False)
                   + f" L{pt((x0 + r + ext, y0))} Z")
        else:
            cap = (f"M{pt((x1 - r - ext, y0 + T))} L{pt((x1 - r, y0 + T))}"
                   + segs_d([kappa_arc((x1 - r, y0 + r), r, 90, 0), kappa_arc((x1 - r, y0 + r), r, 0, -90)], move=False)
                   + f" L{pt((x1 - r - ext, y0))} Z")
        cap = f'<path d="{cap}" fill="{spine_col}"/>'
    return f'<path d="{d}" fill="{C["cover"]}"/>{cap}<path d="{pages}" fill="{C["page"]}"/>{ls}'


# ---------------------------------------------------------------- finish: grain, lit edge, contact shadow, placement

def finish(sc, obj, ground, grain=(0.6, 0.26, -0.11, 0.40, -0.18), lit=(9, 6, 0.75)):
    """The object with paper grain and one lit edge, over a soft contact shadow `ground` = (cx, cy, rx, ry, opacity)."""
    g = grain
    sc.defs.append(f"""
<filter id="{ID}-paper" x="-15%" y="-15%" width="130%" height="130%" color-interpolation-filters="sRGB">
  <feTurbulence type="fractalNoise" baseFrequency="{g[0]}" numOctaves="2" seed="11" result="fine"/>
  <feColorMatrix in="fine" type="matrix" values="0 0 0 0 0.42  0 0 0 0 0.27  0 0 0 0 0.10  {g[1]} 0 0 0 {g[2]}" result="fineA"/>
  <feTurbulence type="fractalNoise" baseFrequency="0.009 0.015" numOctaves="3" seed="4" result="mot"/>
  <feColorMatrix in="mot" type="matrix" values="0 0 0 0 0.55  0 0 0 0 0.36  0 0 0 0 0.14  {g[3]} 0 0 0 {g[4]}" result="motA"/>
  <feMerge result="grain"><feMergeNode in="motA"/><feMergeNode in="fineA"/></feMerge>
  <feComposite in="grain" in2="SourceAlpha" operator="in" result="grainIn"/>
  <feGaussianBlur in="SourceAlpha" stdDeviation="{lit[0]}" result="bump"/>
  <feSpecularLighting in="bump" surfaceScale="{lit[1]}" specularConstant="{lit[2]}" specularExponent="18" lighting-color="#FFF7E6" result="spec">
    <feDistantLight azimuth="270" elevation="40"/>
  </feSpecularLighting>
  <feComposite in="spec" in2="SourceAlpha" operator="in" result="specIn"/>
  <feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="grainIn"/><feMergeNode in="specIn"/></feMerge>
</filter>
<filter id="{ID}-ground" x="-50%" y="-200%" width="200%" height="500%"><feGaussianBlur stdDeviation="{ground[3] * 0.8:.1f}"/></filter>""")
    cx, cy, rx, ry, op = ground
    shadow = f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="#5E3F1A" fill-opacity="{op}" filter="url(#{ID}-ground)"/>'
    return shadow, f'<g filter="url(#{ID}-paper)">{obj}</g>'


def measure(obj_svg, defs):
    """Bounding box and alpha centroid of the bare object, rendered at 512 px."""
    from PIL import Image
    tmp = os.path.join(HERE, ".measure.svg")
    png = os.path.join(HERE, ".measure.png")
    open(tmp, "w").write(f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024"><defs>{defs}</defs>{obj_svg}</svg>')
    kit.render(tmp, png, 512)
    a = Image.open(png).getchannel("A").point(lambda v: 255 if v > 40 else 0)
    bb = a.getbbox()
    w, h = a.size
    px = a.load()
    sx = sy = m = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if px[x, y]:
                sx += x; sy += y; m += 1
    os.remove(tmp); os.remove(png)
    return [v * 2 for v in bb], (sx / m * 2, sy / m * 2)


def build(name, v, fast=False):
    C.clear(); C.update(BASE_C); C.update(v.get("tones", {}))
    sc = Scene()
    obj, ground = v["draw"](sc)
    shadow, body = finish(sc, obj, ground)
    defs = "".join(sc.defs)
    place = v.get("_place")
    if place is None or not fast:
        bb, cen = measure(body, defs)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        k = v.get("fit", 0.64) * 824 / (h if v.get("fit_by") == "height" else max(w, h))
        bc = ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)
        mix = v.get("mix", 0.5)
        ax, ay = bc[0] * mix + cen[0] * (1 - mix), bc[1] * mix + cen[1] * (1 - mix)
        aim = v.get("centre", (512, 502))
        place = (aim[0] - k * ax, aim[1] - k * ay, k)
        v["_place"] = place
        v["_report"] = (f"k {k:.2f}  fill w {k * w / 824:.0%} h {k * h / 824:.0%}  "
                        f"bbox centre ({aim[0] - k * ax + k * bc[0]:.0f},{aim[1] - k * ay + k * bc[1]:.0f})  "
                        f"mass centre ({aim[0] - k * ax + k * cen[0]:.0f},{aim[1] - k * ay + k * cen[1]:.0f})")
    tx, ty, k = place
    inner = f'<g transform="translate({tx:.1f} {ty:.1f}) scale({k:.4f})">{shadow}{body}</g>'
    return kit.tile(inner, defs)


# ---------------------------------------------------------------- round 3: refining V2 ("Tree D")

BASE_C = dict(C)                       # round 2's palette, for the reference
DEEP = dict(                           # move 5: a slightly deeper parchment and a firmer, darker trunk
    leaf_lit="#DBB679", leaf_shade="#C39049", page="#F0E1C0", page_edge="#DCC28F", page_line="#BF9E66",
    fold="#D0B07A", cover="#9A6431", ink="#86501F", ink_deep="#5E3716")
ACCENT = dict(blue="#1A7DA4", redbrown="#7A3B1E")
SPINE_DEEP = "#7A4A22"                 # move 4: the lower book's spine, one tone deeper than the covers


def rrect(x0, y0, W, H, r):
    x1, y1 = x0 + W, y0 + H
    k = r * 0.45
    return (f"M{pt((x0 + r, y0))} L{pt((x1 - r, y0))} C{pt((x1 - k, y0))} {pt((x1, y0 + k))} {pt((x1, y0 + r))}"
            f" L{pt((x1, y1 - r))} C{pt((x1, y1 - k))} {pt((x1 - k, y1))} {pt((x1 - r, y1))}"
            f" L{pt((x0 + r, y1))} C{pt((x0 + k, y1))} {pt((x0, y1 - k))} {pt((x0, y1 - r))}"
            f" L{pt((x0, y0 + r))} C{pt((x0, y0 + k))} {pt((x0 + k, y0))} {pt((x0 + r, y0))} Z")


def spine_book(x0, y0, W, T, col, bands=True):
    """A closed book lying flat with its spine towards us: a long, softly rounded slab,
    with a pair of raised bands near each end (no lettering)."""
    out = f'<path d="{rrect(x0, y0, W, T, min(12, T * 0.2))}" fill="{col}"/>'
    out += (f'<path d="M{pt((x0 + 10, y0 + 6))} L{pt((x0 + W - 10, y0 + 6))} M{pt((x0 + 10, y0 + T - 6))} L{pt((x0 + W - 10, y0 + T - 6))}" '
            f'stroke="#2A1608" stroke-opacity="0.22" stroke-width="2.5" stroke-linecap="round"/>')
    if bands:
        d = ""
        for x in (x0 + W * 0.085, x0 + W * 0.085 + 9, x0 + W * 0.915 - 9, x0 + W * 0.915):
            d += f"M{pt((x, y0 + 7))} L{pt((x, y0 + T - 7))} "
        out += f'<path d="{d}" stroke="#F6E7C6" stroke-opacity="0.32" stroke-width="3" stroke-linecap="round"/>'
    return out


def tree(sc, crown="sprays", books="plain", trunk=1.0, accent=None, veins="text", accent_on="cap"):
    """The tree rooted in two closed books. Every option at its default draws round 2's V2 exactly."""
    ink = C["ink_deep"]
    acc = ACCENT.get(accent) if accent_on == "cap" else None
    low = ACCENT.get(accent, SPINE_DEEP) if accent_on == "spine" else SPINE_DEEP
    if books == "plain":
        bk = (closed_book(262, 700, 500, 84, spine="left", lines=3)
              + closed_book(300, 628, 430, 72, spine="right", lines=2, spine_col=acc))
    else:   # move 4: the lower book spine-on in a deeper tone; the upper one offset, its pages and spine end showing
        bk = (spine_book(262, 704, 500, 80, low)
              + closed_book(318, 628, 432, 76, spine="right", lines=3, spine_col=acc))
    roots = (stem([(500, 631), (466, 627), (430, 632)], 13 * trunk ** 0.5, 3, ink)
             + stem([(524, 631), (558, 627), (596, 632)], 13 * trunk ** 0.5, 3, ink))
    kw = dict(veins=veins)
    if crown == "sprays":   # round 2: three beech sprays and a dog-eared leader, ten leaves
        stem_ = stem([(512, 640), (506, 570), (516, 500), (510, 452)], 38 * trunk, 12 * trunk, ink)
        br = (stem([(510, 520), (474, 488), (440, 466)], 15 * trunk, 7, ink)
              + stem([(514, 494), (552, 466), (586, 452)], 14 * trunk, 7, ink))
        top = (spray(sc, [(440, 468), (408, 440), (382, 424)], 8, 4, [(0.2, -55, 135), (0.55, 52, 140), (1.0, -6, 150)], **kw)
               + spray(sc, [(586, 454), (616, 428), (642, 414)], 8, 4, [(0.2, 55, 135), (0.55, -52, 140), (1.0, 6, 150)], **kw)
               + spray(sc, [(510, 456), (508, 410), (514, 372)], 9, 4, [(0.3, -58, 140), (0.62, 58, 140)], **kw)
               + leaf(sc, (514, 374), 190, 4, petiole=8, fold=(0.80, 14), **kw))
    elif isinstance(crown, dict):   # an explicit crown: branches and leaves
        stem_ = stem(crown["trunk"], 38 * trunk, 11 * trunk, ink)
        br = "".join(stem(b, 15 * trunk, 6, ink) for b in crown["branches"])
        top = "".join(leaf(sc, (x, y), L, a, petiole=8, fold=(0.80, 14) if f else None, **kw) for x, y, L, a, f in crown["leaves"])
    else:   # move 2: five larger leaves in an oval, on short branches that alternate up the leader
        stem_ = stem([(512, 640), (507, 572), (514, 505), (511, 440), (512, 392)], 38 * trunk, 11 * trunk, ink)
        br = (stem([(511, 530), (480, 500), (456, 482)], 15 * trunk, 6, ink)
              + stem([(512, 478), (484, 448), (462, 430)], 14 * trunk, 6, ink)
              + stem([(513, 505), (546, 478), (568, 462)], 15 * trunk, 6, ink)
              + stem([(512, 450), (542, 422), (560, 404)], 14 * trunk, 6, ink))
        top = (leaf(sc, (456, 484), 172, -72, petiole=8, **kw)
               + leaf(sc, (568, 464), 170, 70, petiole=8, **kw)
               + leaf(sc, (462, 432), 186, -42, petiole=8, **kw)
               + leaf(sc, (560, 406), 178, 40, petiole=8, **kw)
               + leaf(sc, (512, 394), 222, 2, petiole=6, fold=(0.80, 14), **kw))
    return bk + roots + stem_ + br + top, (512, 786, 230, 10, 0.16)


def crown_blob(cx, cy, rx, ry, lobes=5, depth=0.07, flat=0.62):
    """The crown as one soft silhouette: an ellipse with a few shallow lobes around its top and a flattened base."""
    pts = []
    n = 72
    for i in range(n):
        t = 2 * math.pi * i / n
        up = max(0.0, -math.sin(t))                       # 1 at the top, 0 on the lower half
        m = 1 + depth * up ** 0.6 * math.cos(lobes * (t + math.pi / 2))
        x, y = cx + rx * m * math.cos(t), cy + ry * m * math.sin(t)
        pts.append((x, min(y, cy + ry * flat)))
    pts.append(pts[0])
    return segs_d(catmull(pts)) + " Z"


def tree_small(sc, accent=None):
    """The same mark for 16-48 px: the crown as one soft five-lobed silhouette in a single parchment tone,
    a heavier trunk, and the books as two clean slabs (the blue spine end kept)."""
    ink = C["ink_deep"]
    bk = (f'<path d="{rrect(262, 700, 500, 88, 14)}" fill="{SPINE_DEEP}"/>'
          + closed_book(318, 616, 432, 92, spine="right", lines=0, cover=17, spine_col=ACCENT.get(accent)))
    stem_ = stem([(512, 630), (508, 570), (513, 500)], 62, 34, ink)
    top = f'<path d="{crown_blob(512, 436, 168, 150)}" fill="{C["leaf_shade"]}"/>'
    return bk + stem_ + top, (512, 790, 230, 10, 0.16)


REF = dict(fit=0.64, centre=(512, 502), mix=0.5)                      # round 2's placement
VISUAL = dict(fit=0.64, fit_by="height", centre=(512, 506), mix=1.0)  # move 3: box centre just above the middle

VARIANTS = [
    ("v2", dict(draw=lambda sc: tree(sc), **REF),
     "Round 2's V2 as it was, for reference."),
    ("crown", dict(draw=lambda sc: tree(sc, crown="calm"), **REF),
     "Calmer crown: five larger leaves in one clear dome, still alternate like a beech's."),
    ("place", dict(draw=lambda sc: tree(sc), **VISUAL),
     "Placement: lowered onto the tile's visual centre, filling 64% of its height."),
    ("books", dict(draw=lambda sc: tree(sc, books="character"), **REF),
     "Books: the lower one spine-on in a deeper tone with raised bands; the upper offset, pages showing."),
    ("presence", dict(draw=lambda sc: tree(sc, trunk=1.25), tones=DEEP, **REF),
     "Dock presence: a deeper parchment and a firmer trunk. No gradient wash."),
    ("accent-blue", dict(draw=lambda sc: tree(sc, accent="blue"), **REF),
     "Accent: the upper book's spine in Daf's blue, like Moshe's eye dot."),
    ("accent-redbrown", dict(draw=lambda sc: tree(sc, accent="redbrown"), **REF),
     "Accent: the upper book's spine in a deep red-brown."),
    ("final", dict(draw=lambda sc: tree(sc, crown="calm", books="character", trunk=1.25, accent="blue"), tones=DEEP, **VISUAL),
     "Recommended: moves 2-5 together, with the blue spine end as the one accent."),
]
LABELS = ["1  V2", "2  Crown", "3  Placement", "4  Books", "5  Presence", "6a  Blue spine", "6b  Red-brown spine", "7  Final"]
SMALL = dict(draw=lambda sc: tree_small(sc, accent="blue"), tones=DEEP, **VISUAL)


def small_sheet(big, small, out, sizes=(16, 24, 32, 48), zoom=4):
    """final and final-small at 16/24/32/48 on light and dark, at true size and magnified (nearest neighbour)."""
    from PIL import Image, ImageDraw
    tmp = os.path.join(HERE, ".s.png")
    tiles = {}
    for key, svg in (("final", big), ("final-small", small)):
        for n in sizes:
            kit.render(svg, tmp, n)
            tiles[key, n] = Image.open(tmp).convert("RGBA")
    os.remove(tmp)
    pad = 18
    cell = max(sizes) + pad
    zcell = max(sizes) * zoom + pad
    W = pad + 110 + len(sizes) * cell + pad + len(sizes) * zcell
    H = pad + 2 * (2 * (zcell) + pad) + 30
    img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    dr = ImageDraw.Draw(img)
    y = pad
    for bg, fg in (((244, 244, 244, 255), (60, 60, 60)), ((30, 30, 30, 255), (220, 220, 220))):
        dr.rectangle([0, y - pad // 2, W, y + 2 * zcell + pad // 2], fill=bg)
        for r, key in enumerate(("final", "final-small")):
            ry = y + r * zcell
            dr.text((pad, ry + zcell // 2 - 6), key, fill=fg)
            for i, n in enumerate(sizes):
                im = tiles[key, n]
                img.alpha_composite(im, (pad + 110 + i * cell + (max(sizes) - n) // 2, ry + (zcell - n) // 2))
                z = im.resize((n * zoom, n * zoom), Image.NEAREST)
                x = pad + 110 + len(sizes) * cell + pad + i * zcell
                img.alpha_composite(z, (x + (max(sizes) - n) * zoom // 2, ry + (zcell - n * zoom) // 2))
        y += 2 * zcell + pad
    dr.text((pad, H - 22), "true size: 16 24 32 48            magnified x4 (nearest neighbour): 16 24 32 48", fill=(90, 90, 90))
    img.save(out)


def main():
    paths = []
    for name, v, _ in VARIANTS:
        p = os.path.join(HERE, f"{name}.svg")
        open(p, "w").write(build(name, v))
        print(f"{name:16s}", v["_report"])
        paths.append(p)
    final, final_small = paths[-1], os.path.join(HERE, "final-small.svg")   # the "final" variant is final.svg
    open(final_small, "w").write(build("final-small", SMALL))
    print(f"{'final-small':16s}", SMALL["_report"])
    kit.sheet(os.path.join(HERE, "sheet.png"), paths, LABELS, [t for _, _, t in VARIANTS])
    small_sheet(final, final_small, os.path.join(HERE, "small.png"))
    kit.render(final, os.path.join(HERE, "final-1024.png"), 1024)


if __name__ == "__main__":
    main()
