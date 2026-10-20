#!/usr/bin/env python3
"""Daf icon, round 1, concept 6: the leaf that is a page.

A single dry leaf in parchment tones. Its midrib is a book's gutter, the two halves are the
facing pages, and the side veins are faint lines of text running out from the gutter.

    python3 make.py [vN]       # writes v1.svg v2.svg v3.svg, sheet.png and best-1024.png (of vN, default v2)

Everything is drawn in a local frame: the leaf's base at (0, 0), its tip at (0, -L), the left
half at x < 0. A group transform places and tilts it on the 1024 canvas. Filters (grain, lit
edge, contact shadow) sit on untransformed groups so the light always comes from above.
"""
import math
import os
import sys

sys.path.insert(0, "/srv/dev/daf/design/icon")
import kit  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ID = "leaf"


# ---------------------------------------------------------------- geometry helpers

def fmt(v):
    return f"{v:.1f}".rstrip("0").rstrip(".") if abs(v) > 1e-9 else "0"


def pt(p):
    return f"{fmt(p[0])},{fmt(p[1])}"


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


# ---------------------------------------------------------------- the leaf

def midrib(L, bow):
    return [((0, 0), (bow, -L / 3), (bow * 0.9, -2 * L / 3), (0, -L))]


def half_outline(L, h, side):
    """One half's margin from base to tip. `h` holds the shape of that half."""
    w, p = h["w"], h["p"]
    bx, by = h["base"]          # base handle: fractions of w and L (by < 0 dips below the base: cordate)
    ka, kb = h["ka"], h["kb"]   # handle lengths into and out of the widest point
    tx, ty = h["tip"]           # tip handle: how the margin runs into the point
    s = side
    st = h.get("start", 0.0)     # where this half joins the midrib (elm: the halves start unevenly)
    W = (s * w, -p * L)
    a = ((0, -st * L), (s * w * bx, -L * by - st * L), (s * w, -p * L + (p - st) * L * ka), W)
    b = (W, (s * w, -p * L - (1 - p) * L * kb), (s * w * tx, -L + L * ty), (0, -L))
    return [a, b]


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


# ---------------------------------------------------------------- the icon

def build(v):
    """The icon's SVG. Runs twice: the first pass finds the scale, the second keeps line weights in screen pixels."""
    if "_k" not in v:
        v["_k"] = 1.0
        _build(v)
    return _build(v)


def _build(v):
    L = v["L"]
    kk = v["_k"]
    rib = midrib(L, v["bow"])
    halves = {}
    margins = {}
    for side, key in ((-1, "left"), (1, "right")):
        segs = half_outline(L, v[key], side)
        if v.get("wave"):
            segs = wavy(segs, v["wave"], v["wave_period"], v.get("wave_phase", 0) + (0.9 if side > 0 else 0), side=-side)
        margins[key] = segs
    # the shadow always falls from the leaf as it would lie flat
    flat_sil = ("M0,0 L" if v["left"].get("start") else "M") + segs_d(margins["left"])[1:] + segs_d(reverse(margins["right"]), move=False) + " Z"
    # `lift`: the right half rises off the midrib like a page being turned, so it looks narrower
    lift = v.get("lift", 1.0)
    sx = lambda p: (p[0] * lift, p[1]) if p[0] > 0 else p  # noqa: E731
    if lift != 1.0:
        margins["right"] = [tuple((q[0] * lift, q[1]) for q in s) for s in margins["right"]]
    for key in ("left", "right"):
        halves[key] = segs_d(margins[key]) + segs_d(reverse(rib), move=False) + " Z"
    # whole silhouette: left margin up to the tip, right margin back down
    sil = segs_d(margins["left"]) + segs_d(reverse(margins["right"]), move=False) + " Z"
    if v["left"].get("start"):
        sil = "M0,0 L" + sil[1:]

    # petiole: a short tapered stalk below the base
    pl, pw, pc = v["stalk"]
    pw /= kk
    s0, s1 = pw / 2, pw * 0.32
    stalk = (f"M{pt((-s0, -6))} C{pt((-s0 * 0.9, pl * 0.4))} {pt((pc - s1 - 2, pl * 0.7))} {pt((pc - s1, pl))}"
             f" Q{pt((pc, pl + s1 * 1.6))} {pt((pc + s1, pl))}"
             f" C{pt((pc + s1 + 2, pl * 0.7))} {pt((s0 * 0.9, pl * 0.4))} {pt((s0, -6))} Z")

    col = v["col"]
    rot = v["rot"]

    # midrib: tapered, from the base (thick) to the tip (fine)
    mw0, mw1 = v["rib_w"][0] / kk, v["rib_w"][1] / kk
    rp = sample(rib, 30)
    left_edge, right_edge = [], []
    for i, p in enumerate(rp):
        t = i / (len(rp) - 1)
        hw = (mw0 + (mw1 - mw0) * t ** 0.8) / 2
        q = rp[min(i + 1, len(rp) - 1)] if i < len(rp) - 1 else p
        r = rp[i - 1] if i > 0 else p
        tg = (q[0] - r[0], q[1] - r[1])
        ln = math.hypot(*tg) or 1
        n = (-tg[1] / ln, tg[0] / ln)
        left_edge.append((p[0] - n[0] * hw, p[1] - n[1] * hw))
        right_edge.append((p[0] + n[0] * hw, p[1] + n[1] * hw))
    rib_d = segs_d(catmull(left_edge)) + " L" + pt(right_edge[-1]) + segs_d(reverse(catmull(right_edge)), move=False) + " Z"

    # veins as lines of text: evenly spaced, nearly straight, ragged ends like a paragraph's
    veins = []
    for side, key in ((-1, "left"), (1, "right")):
        cfg = v["veins"][key]
        n = len(cfg["len"])
        poly = sample(margins[key], 60)
        if key == "right" and lift != 1.0:
            poly = [(q[0] / lift, q[1]) for q in poly]
        for i in range(n):
            s = cfg["from"] + (cfg["to"] - cfg["from"]) * i / max(n - 1, 1)
            o = cubic(rib[0], s)
            o = (o[0] + side * cfg.get("gap", mw0 * 0.3), o[1])
            a = math.radians(cfg["angle"] + cfg.get("fan", 0) * (i / max(n - 1, 1) - 0.5))
            d = (side * math.cos(a), -math.sin(a))
            hit = ray_hit(o, d, poly)
            if hit is None:
                continue
            ln = hit * cfg["len"][i]
            e = (o[0] + d[0] * ln, o[1] + d[1] * ln)
            bend = cfg.get("bend", 0) * ln
            c1 = (o[0] + d[0] * ln * 0.35, o[1] + d[1] * ln * 0.35 - cfg.get("kick", 0) * ln)
            c2 = (o[0] + d[0] * ln * 0.7, o[1] + d[1] * ln * 0.7 - bend)
            e = (e[0], e[1] - bend * 1.4)
            if side > 0:
                o, c1, c2, e = sx(o), sx(c1), sx(c2), sx(e)
            veins.append(f"M{pt(o)} C{pt(c1)} {pt(c2)} {pt(e)}")
    vein_d = " ".join(veins)

    # optional dog-ear at the tip: the body is cut along a fold line, the cut-off tip flipped over
    fold = v.get("fold")
    extra_defs = ""
    flap = ""
    flap_shadow = ""
    shadow_shape = f'<path d="{flat_sil}"/>'
    rot_r = math.radians(rot)
    if fold:
        q, ang = fold["at"], fold["angle"]
        R = reflect_matrix(q, ang)
        extra_defs = (f'<clipPath id="{ID}-body"><path d="{halfplane(q, ang, 1)}"/></clipPath>'
                      f'<clipPath id="{ID}-flapcut"><path d="{halfplane(q, ang, -1)}"/></clipPath>'
                      f'<linearGradient id="{ID}-flapg" gradientUnits="userSpaceOnUse" x1="{fmt(q[0])}" y1="{fmt(q[1])}" x2="0" y2="{fmt(-L)}">'
                      f'<stop offset="0" stop-color="{col["fold"]}"/><stop offset="{fold.get("soft", 0.5)}" stop-color="{col["back"]}"/></linearGradient>')
        flap_shape = f'<g transform="{R}"><path d="{sil}" clip-path="url(#{ID}-flapcut)"/></g>'
        flap = f'<g transform="{R}"><path d="{sil}" clip-path="url(#{ID}-flapcut)" fill="url(#{ID}-flapg)"/></g>'
        # the flap's own small shadow, cast straight down in screen space, falling on the blade only
        blur, sdy = fold.get("shadow", (6, 7))[0:2]
        ldx, ldy = sdy * math.sin(rot_r), sdy * math.cos(rot_r)   # straight down on screen, in the leaf's frame
        extra_defs += (f'<filter id="{ID}-flapsh" x="-40%" y="-40%" width="180%" height="180%">'
                       f'<feGaussianBlur in="SourceAlpha" stdDeviation="{blur}"/><feOffset dx="{ldx:.1f}" dy="{ldy:.1f}" result="b"/>'
                       f'<feFlood flood-color="#6B4A22" flood-opacity="{fold.get("shadow", (6, 7, 0.3))[2]}"/><feComposite in2="b" operator="in"/></filter>')
        flap_shadow = f'<g clip-path="url(#{ID}-blade)"><g clip-path="url(#{ID}-body)"><g filter="url(#{ID}-flapsh)">{flap_shape}</g></g></g>'
        shadow_shape = f'<g clip-path="url(#{ID}-body)"><path d="{flat_sil}"/></g>{flap_shape}'

    # gutter shading: a blurred band along the midrib, clipped to the blade
    g_w, g_op = v["gutter"]

    g = v.get("grain", (0.9, 0.42, -0.18, 0.55, -0.24))
    defs = f"""
<clipPath id="{ID}-blade"><path d="{sil}"/></clipPath>{extra_defs}
<filter id="{ID}-shadow" x="-30%" y="-30%" width="160%" height="160%">
  <feGaussianBlur in="SourceAlpha" stdDeviation="{v['shadow'][1]}"/>
  <feOffset dy="{v['shadow'][0]}" result="b"/>
  <feFlood flood-color="#6B4A22" flood-opacity="{v['shadow'][2]}"/>
  <feComposite in2="b" operator="in"/>
</filter>
<filter id="{ID}-soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="{g_w * 0.32 / kk:.1f}"/></filter>
<filter id="{ID}-paper" x="-15%" y="-15%" width="130%" height="130%" color-interpolation-filters="sRGB">
  <feTurbulence type="fractalNoise" baseFrequency="{g[0]}" numOctaves="2" seed="11" result="fine"/>
  <feColorMatrix in="fine" type="matrix" values="0 0 0 0 0.42  0 0 0 0 0.27  0 0 0 0 0.10  {g[1]} 0 0 0 {g[2]}" result="fineA"/>
  <feTurbulence type="fractalNoise" baseFrequency="0.009 0.015" numOctaves="3" seed="4" result="mot"/>
  <feColorMatrix in="mot" type="matrix" values="0 0 0 0 0.55  0 0 0 0 0.36  0 0 0 0 0.14  {g[3]} 0 0 0 {g[4]}" result="motA"/>
  <feMerge result="grain"><feMergeNode in="motA"/><feMergeNode in="fineA"/></feMerge>
  <feComposite in="grain" in2="SourceAlpha" operator="in" result="grainIn"/>
  <feGaussianBlur in="SourceAlpha" stdDeviation="{v['lit'][0]}" result="bump"/>
  <feSpecularLighting in="bump" surfaceScale="{v['lit'][1]}" specularConstant="{v['lit'][2]}" specularExponent="18" lighting-color="#FFF7E6" result="spec">
    <feDistantLight azimuth="270" elevation="40"/>
  </feSpecularLighting>
  <feComposite in="spec" in2="SourceAlpha" operator="in" result="specIn"/>
  <feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="grainIn"/><feMergeNode in="specIn"/></feMerge>
</filter>"""

    blade = (f'<path d="{halves["left"]}" fill="{col["left"]}"/>'
             f'<path d="{halves["right"]}" fill="{col["right"]}"/>'
             f'<g clip-path="url(#{ID}-blade)"><path d="{segs_d(rib)}" fill="none" stroke="{col["gutter"]}" stroke-width="{g_w / kk:.1f}" '
             f'stroke-opacity="{g_op}" filter="url(#{ID}-soft)"/></g>'
             f'<path d="{vein_d}" fill="none" stroke="{col["line"]}" stroke-width="{v["vein_w"] / kk:.2f}" stroke-linecap="round" stroke-opacity="{v["vein_op"]}"/>'
             f'<path d="{rib_d}" fill="{col["line"]}"/>')
    if fold:
        blade = f'<g clip-path="url(#{ID}-body)">{blade}</g>{flap_shadow}'

    # report: bounding box (as a share of the 824 tile) and the blade's centroid, in canvas pixels
    poly = sample(margins["left"], 40) + list(reversed(sample(margins["right"], 40)))
    if fold:
        q, ang = fold["at"], fold["angle"]
        dd = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        nn = (-dd[1], dd[0])
        keep = [p for p in poly if (p[0] - q[0]) * nn[0] + (p[1] - q[1]) * nn[1] >= 0]
        r00, r01 = dd[0] ** 2 - dd[1] ** 2, 2 * dd[0] * dd[1]
        refl = [(q[0] + r00 * (p[0] - q[0]) + r01 * (p[1] - q[1]), q[1] + r01 * (p[0] - q[0]) - r00 * (p[1] - q[1]))
                for p in poly if (p[0] - q[0]) * nn[0] + (p[1] - q[1]) * nn[1] < 0]
        pts_all = keep + refl
    else:
        pts_all = poly
    pts_all = pts_all + [(pc, pl)]
    # placement: scale so the larger side fills `fit` of the 824 tile, and put the point halfway
    # between the bounding-box centre and the blade's centroid on the optical centre
    c_, s_ = math.cos(rot_r), math.sin(rot_r)
    R0 = lambda p: (c_ * p[0] - s_ * p[1], s_ * p[0] + c_ * p[1])  # noqa: E731
    g0 = [R0(p) for p in pts_all]
    xs, ys = [p[0] for p in g0], [p[1] for p in g0]
    k = v.get("fit", 0.64) * 824 / max(max(xs) - min(xs), max(ys) - min(ys))
    gp = [R0(p) for p in poly]
    A = Cx = Cy = 0.0
    for (x0, y0), (x1, y1) in zip(gp, gp[1:] + gp[:1]):
        cr = x0 * y1 - x1 * y0
        A += cr; Cx += (x0 + x1) * cr; Cy += (y0 + y1) * cr
    cen = (Cx / (3 * A), Cy / (3 * A))
    bc = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    aim = v.get("centre", (512, 500))
    wb = v.get("centre_mix", 0.5)
    px_ = (bc[0] * wb + cen[0] * (1 - wb)) * k
    py_ = (bc[1] * wb + cen[1] * (1 - wb)) * k
    tx, ty = aim[0] - px_, aim[1] - py_
    v["_k"] = k
    T = f"translate({tx:.1f} {ty:.1f}) scale({k:.4f}) rotate({fmt(rot)})"
    G = lambda p: (tx + k * p[0], ty + k * p[1])  # noqa: E731
    v["_report"] = (f"k {k:.2f}  bbox x {G((min(xs), 0))[0]:.0f}-{G((max(xs), 0))[0]:.0f} y {G((0, min(ys)))[1]:.0f}-{G((0, max(ys)))[1]:.0f}  "
                    f"fill w {k * (max(xs) - min(xs)) / 824:.0%} h {k * (max(ys) - min(ys)) / 824:.0%}  "
                    f"bbox centre ({G(bc)[0]:.0f},{G(bc)[1]:.0f})  blade centroid ({G(cen)[0]:.0f},{G(cen)[1]:.0f})")

    inner = (f'<g filter="url(#{ID}-shadow)"><g transform="{T}">{shadow_shape}<path d="{stalk}"/></g></g>'
             f'<g filter="url(#{ID}-paper)"><g transform="{T}">'
             f'<path d="{stalk}" fill="{col["line"]}"/>{blade}{flap}</g></g>')
    return kit.tile(inner, defs)


# ---------------------------------------------------------------- the three variations

TONES = dict(left="#E7CF9F", right="#D3AD70", gutter="#A87B42", line="#9E6A32", back="#F2E7CF", fold="#D7BC88")

# Shared beech blade: ovate, widest a little below the middle, rounded base, acute tip.
BEECH_L = dict(w=190, p=0.44, base=(0.62, 0.0), ka=0.62, kb=0.46, tip=(0.12, 0.18))
BEECH_R = dict(w=182, p=0.46, base=(0.56, 0.01), ka=0.62, kb=0.46, tip=(0.11, 0.20))
LINES_L = dict(**{"from": 0.12, "to": 0.82}, angle=20, fan=10, bend=0.03, gap=9, len=[0.84, 0.86, 0.83, 0.87, 0.85, 0.56, 0.84, 0.80, 0.62])
LINES_R = dict(**{"from": 0.14, "to": 0.82}, angle=20, fan=10, bend=0.03, gap=9, len=[0.86, 0.83, 0.87, 0.60, 0.85, 0.84, 0.86, 0.66, 0.70])
TEXT = dict(angle=6, fan=6, kick=0.10, bend=0.0)   # veins turned into lines of text: nearly square to the gutter
LIT = (10, 7, 0.8)       # lit edge: bump blur, surface scale, specular strength
GRAIN = (0.6, 0.28, -0.12, 0.42, -0.19)  # fine-grain frequency and alpha ramp, then mottling alpha ramp

V1 = dict(  # beech, upright, the spread: two facing pages, one in light and one in shade, with a soft gutter
    L=490, bow=5, mass=0.43, rot=0, fit=0.68,
    left=BEECH_L, right=BEECH_R, wave=1.6, wave_period=50,
    stalk=(62, 16, 5), rib_w=(8, 2.5),
    veins=dict(left=dict(LINES_L, **TEXT), right=dict(LINES_R, **TEXT)),
    vein_w=5.5, vein_op=0.45, gutter=(110, 0.8),
    col=TONES, shadow=(12, 14, 0.2), lit=LIT, grain=GRAIN)

V2 = dict(  # beech on the diagonal, veins at their natural angle, its tip folded over like a dog-eared page corner
    L=540, bow=-6, mass=0.45, rot=38, fit=0.66,
    left=dict(BEECH_L, w=160, p=0.45, kb=0.42, tip=(0.10, 0.20)), right=dict(BEECH_R, w=152, p=0.46, kb=0.42, tip=(0.08, 0.22)),
    wave=1.6, wave_period=50,
    stalk=(58, 16, -12), rib_w=(9, 2.5),
    veins=dict(left=dict(LINES_L, to=0.72, len=LINES_L["len"][:8]), right=dict(LINES_R, to=0.72, len=LINES_R["len"][:8])),
    vein_w=5.5, vein_op=0.45, gutter=(80, 0.6),
    fold=dict(at=(0, -395), angle=18, soft=0.55, shadow=(6, 7, 0.34)),
    col=TONES, shadow=(12, 14, 0.2), lit=LIT, grain=GRAIN)

ELM_L = dict(w=176, p=0.46, base=(0.70, 0.02), ka=0.66, kb=0.42, tip=(0.06, 0.17), start=0.07)
ELM_R = dict(w=160, p=0.42, base=(0.42, 0.06), ka=0.62, kb=0.44, tip=(0.05, 0.18))

V3 = dict(  # elm, tilted right, the most page-like: lines of text across, a deep gutter, the tip folded down flat
    L=530, bow=-7, mass=0.42, rot=14, fit=0.68,
    left=ELM_L, right=ELM_R, wave=1.6, wave_period=46,
    stalk=(50, 16, -7), rib_w=(8, 2.5),
    veins=dict(left=dict(LINES_L, **{"from": 0.15, "to": 0.74}, **TEXT), right=dict(LINES_R, **{"from": 0.11, "to": 0.74}, **TEXT)),
    vein_w=5.5, vein_op=0.45, gutter=(100, 0.75),
    fold=dict(at=(0, -424), angle=-14, soft=0.55, shadow=(6, 7, 0.34)),
    col=TONES, shadow=(12, 14, 0.2), lit=LIT, grain=GRAIN)

VARIANTS = [
    ("v1", V1, "Beech, upright: two facing pages, one lit and one in shade, veins as lines of text."),
    ("v2", V2, "Beech on the diagonal, natural veins: its tip folded over like a dog-eared page corner."),
    ("v3", V3, "Elm, tilted right: lines of text, a deep gutter, the tip folded flat like a page top."),
]


def main(which=None):
    paths = []
    for name, v, _ in VARIANTS:
        p = os.path.join(HERE, f"{name}.svg")
        open(p, "w").write(build(v))
        print(name, v["_report"])
        paths.append(p)
    kit.sheet(os.path.join(HERE, "sheet.png"), paths, [n.upper() for n, _, _ in VARIANTS], [t for _, _, t in VARIANTS])
    best = which or "v2"
    kit.render(os.path.join(HERE, f"{best}.svg"), os.path.join(HERE, "best-1024.png"), 1024)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
