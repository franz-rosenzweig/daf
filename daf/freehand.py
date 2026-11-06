"""perfect-freehand 1.2.3 (https://github.com/steveruizok/perfect-freehand, MIT, (c) 2021 Stephen Ruiz
Ltd), in Python: the outline of a stroke drawn with pressure, so the server can draw a Sketchbook
page's strokes into the SVG files it writes to the vault (sketchvault.py) as the pages draw them
(web/vendor/freehand.js) and as Obsidian's Ink plugin does. A line-for-line port of its
getStrokePoints and getStrokeOutlinePoints."""
import math

FIXED_PI = math.pi + 1e-4
_DEFAULT_PRESSURE = 0.5


def _add(a, b): return [a[0] + b[0], a[1] + b[1]]
def _sub(a, b): return [a[0] - b[0], a[1] - b[1]]
def _mul(a, n): return [a[0] * n, a[1] * n]
def _neg(a): return [-a[0], -a[1]]
def _per(a): return [a[1], -a[0]]
def _dpr(a, b): return a[0] * b[0] + a[1] * b[1]
def _len(a): return math.hypot(a[0], a[1])
def _dist(a, b): return math.hypot(a[1] - b[1], a[0] - b[0])
def _dist2(a, b): return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
def _lrp(a, b, t): return _add(a, _mul(_sub(b, a), t))
def _prj(a, b, c): return _add(a, _mul(b, c))


def _uni(a):
    n = _len(a)
    return [a[0] / n, a[1] / n] if n else [a[0] / n if n else 0.0, a[1] / n if n else 0.0]


def _rot(a, c, r):
    s, co = math.sin(r), math.cos(r)
    px, py = a[0] - c[0], a[1] - c[1]
    return [px * co - py * s + c[0], px * s + py * co + c[1]]


def _simulate(prev, distance, size):
    sp = min(1, distance / size)
    rp = min(1, 1 - sp)
    return min(1, prev + (rp - prev) * (sp * 0.275))


def _radius(size, thinning, pressure, easing):
    return size * easing(0.5 - thinning * (0.5 - pressure))


def _taper(t, size, total):
    if t is False or t is None:
        return 0
    if t is True:
        return max(size, total)
    return t


def stroke_points(points, streamline=0.5, size=16, last=False):
    if not points:
        return []
    t = 0.15 + (1 - streamline) * 0.85
    pts = [list(p) for p in points]
    if len(pts) == 2:
        end = pts[1]
        pts = pts[:-1]
        for i in range(1, 5):
            pts.append(_lrp(pts[0], end, i / 4) + list(pts[0][2:]))
    if len(pts) == 1:
        pts = [pts[0], _add(pts[0], [1, 1]) + list(pts[0][2:])]
    out = [{"point": [pts[0][0], pts[0][1]], "pressure": pts[0][2] if len(pts[0]) > 2 and pts[0][2] >= 0 else 0.25,
            "vector": [1, 1], "distance": 0, "running": 0}]
    reached, running, prev, mx = False, 0, out[0], len(pts) - 1
    for i in range(1, len(pts)):
        point = [pts[i][0], pts[i][1]] if last and i == mx else _lrp(prev["point"], pts[i], t)
        if point[0] == prev["point"][0] and point[1] == prev["point"][1]:
            continue
        d = _dist(point, prev["point"])
        running += d
        if i < mx and not reached:
            if running < size:
                continue
            reached = True
        prev = {"point": point, "pressure": pts[i][2] if len(pts[i]) > 2 and pts[i][2] >= 0 else _DEFAULT_PRESSURE,
                "vector": _uni(_sub(prev["point"], point)), "distance": d, "running": running}
        out.append(prev)
    out[0]["vector"] = out[1]["vector"] if len(out) > 1 else [0, 0]
    return out


def outline(points, size=16, thinning=0.5, smoothing=0.5, simulate=True, easing=lambda t: t,
            start=None, end=None, last=False):
    start, end = start or {}, end or {}
    cap_start, cap_end = start.get("cap", True), end.get("cap", True)
    ease_start = start.get("easing") or (lambda t: t * (2 - t))
    ease_end = end.get("easing") or (lambda t: (t - 1) ** 3 + 1)
    if not points or size <= 0:
        return []
    total = points[-1]["running"]
    taper_start, taper_end = _taper(start.get("taper"), size, total), _taper(end.get("taper"), size, total)
    min_d = (size * smoothing) ** 2
    left, right = [], []
    prev_p = points[0]["pressure"]
    for c in points[:10]:
        pr = _simulate(prev_p, c["distance"], size) if simulate else c["pressure"]
        prev_p = (prev_p + pr) / 2
    radius = _radius(size, thinning, points[-1]["pressure"], easing)
    first_r = None
    prev_v = points[0]["vector"]
    pl = points[0]["point"]
    pr_ = pl
    tl, tr = pl, pr_
    sharp_prev = False
    n = len(points)
    for i in range(n):
        pressure = points[i]["pressure"]
        point, vector, distance, running = points[i]["point"], points[i]["vector"], points[i]["distance"], points[i]["running"]
        is_last = i == n - 1
        if not is_last and total - running < 3:
            continue
        if thinning:
            if simulate:
                pressure = _simulate(prev_p, distance, size)
            radius = _radius(size, thinning, pressure, easing)
        else:
            radius = size / 2
        if first_r is None:
            first_r = radius
        ts = ease_start(running / taper_start) if running < taper_start else 1
        te = ease_end((total - running) / taper_end) if total - running < taper_end else 1
        radius = max(0.01, radius * min(ts, te))
        next_v = (points[i] if is_last else points[i + 1])["vector"]
        next_dpr = 1.0 if is_last else _dpr(vector, next_v)
        sharp = _dpr(vector, prev_v) < 0 and not sharp_prev
        sharp_next = next_dpr is not None and next_dpr < 0
        if sharp or sharp_next:
            off = _mul(_per(prev_v), radius)
            step, t = 1 / 13, 0.0
            while t <= 1:
                tl = _rot(_sub(point, off), point, FIXED_PI * t)
                left.append(tl)
                tr = _rot(_add(point, off), point, FIXED_PI * -t)
                right.append(tr)
                t += step
            pl, pr_ = tl, tr
            if sharp_next:
                sharp_prev = True
            continue
        sharp_prev = False
        if is_last:
            off = _mul(_per(vector), radius)
            left.append(_sub(point, off))
            right.append(_add(point, off))
            continue
        off = _mul(_per(_lrp(next_v, vector, next_dpr)), radius)
        tl = _sub(point, off)
        if i <= 1 or _dist2(pl, tl) > min_d:
            left.append(tl)
            pl = tl
        tr = _add(point, off)
        if i <= 1 or _dist2(pr_, tr) > min_d:
            right.append(tr)
            pr_ = tr
        prev_p = pressure
        prev_v = vector
    first = points[0]["point"][:2]
    lastp = points[-1]["point"][:2] if n > 1 else _add(points[0]["point"], [1, 1])
    start_cap, end_cap = [], []
    if n == 1:
        if not (taper_start or taper_end) or last:
            step = 1 / 13
            s = _prj(first, _uni(_per(_sub(first, _add(first, [1, 1])))), -(first_r or radius))
            dots, t = [], step
            while t <= 1:
                dots.append(_rot(s, first, FIXED_PI * 2 * t))
                t += step
            return dots
    else:
        if taper_start or (taper_end and n == 1):
            pass
        elif cap_start and right:
            step, t = 1 / 13, 1 / 13
            while t <= 1:
                start_cap.append(_rot(right[0], first, FIXED_PI * t))
                t += step
        elif left and right:
            cv = _sub(left[0], right[0])
            a, b = _mul(cv, 0.5), _mul(cv, 0.51)
            start_cap += [_sub(first, a), _sub(first, b), _add(first, b), _add(first, a)]
        direction = _per(_neg(points[-1]["vector"]))
        if taper_end or (taper_start and n == 1):
            end_cap.append(lastp)
        elif cap_end:
            s = _prj(lastp, direction, radius)
            step, t = 1 / 29, 1 / 29
            while t < 1:
                end_cap.append(_rot(s, lastp, FIXED_PI * 3 * t))
                t += step
        else:
            end_cap += [_add(lastp, _mul(direction, radius)), _add(lastp, _mul(direction, radius * 0.99)),
                        _sub(lastp, _mul(direction, radius * 0.99)), _sub(lastp, _mul(direction, radius))]
    return left + end_cap + right[::-1] + start_cap


def get_stroke(points, **o):
    return outline(stroke_points(points, o.get("streamline", 0.5), o.get("size", 16), o.get("last", False)),
                   size=o.get("size", 16), thinning=o.get("thinning", 0.5), smoothing=o.get("smoothing", 0.5),
                   simulate=o.get("simulate", True), easing=o.get("easing") or (lambda t: t),
                   start=o.get("start"), end=o.get("end"), last=o.get("last", False))


def svg_path(pts, closed=True):
    """The outline as an SVG path, as Ink writes it (quadratic curves through the midpoints)."""
    if len(pts) < 4:
        return ""
    a, b, c = pts[0], pts[1], pts[2]
    f = lambda v: f"{v:.2f}"
    out = [f"M{f(a[0])},{f(a[1])} Q{f(b[0])},{f(b[1])} {f((b[0] + c[0]) / 2)},{f((b[1] + c[1]) / 2)} T"]
    for i in range(2, len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        out.append(f"{f((a[0] + b[0]) / 2)},{f((a[1] + b[1]) / 2)} ")
    return "".join(out) + ("Z" if closed else "")
