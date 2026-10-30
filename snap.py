"""snap.py - the "hold to snap" brain, like Apple Pencil.

You draw a wobbly line, circle, rectangle... and HOLD STILL at the end. FIVES then
cleans the stroke up: a straight line, a perfect circle or ellipse, a neat triangle or
rectangle. Anything else just gets smoothed.

This file only does the thinking (no mouse, no camera), so it is easy to test.
All points here are screen pixels: (x, y).

Two parts:
  Snapper   - watches the stroke while the pen is down and says when you have held still.
  recognize - looks at the finished stroke and returns (name, clean_points).
"""

import math


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def path_length(pts):
    return sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


# ---------------------------------------------------------------------------
# watching the stroke
# ---------------------------------------------------------------------------
class Snapper:
    """Records the stroke while the pen is down and notices when you hold still.

    Call add(t, point) every frame while ink is down. ready(t) turns True once the pen
    has stayed inside `hold_radius` pixels for `hold_seconds` (and the stroke is long
    enough that it isn't just a dot). stroke() is the stroke up to where the hold began,
    so the little still-pause at the end is not part of the shape.
    """

    def __init__(self, hold_seconds=0.7, hold_radius=12.0, min_length=60.0):
        self.hold_seconds = hold_seconds
        self.hold_radius = hold_radius
        self.min_length = min_length
        self.reset()

    def reset(self):
        self.pts = []
        self.anchor = None       # where the current "stillness" began
        self.anchor_t = 0.0
        self.anchor_i = 0        # index in pts of the anchor

    def add(self, t, p):
        if not self.pts or dist(p, self.pts[-1]) >= 1.0:
            self.pts.append(p)
        if self.anchor is None or dist(p, self.anchor) > self.hold_radius:
            self.anchor = p
            self.anchor_t = t
            self.anchor_i = len(self.pts) - 1

    def stroke(self):
        return self.pts[:self.anchor_i + 1]

    def ready(self, t):
        if self.anchor is None or t - self.anchor_t < self.hold_seconds:
            return False
        return path_length(self.stroke()) >= self.min_length

    def rearm(self, t):
        """Held still but nothing to snap: start counting again."""
        self.anchor_t = t


# ---------------------------------------------------------------------------
# helpers for shapes
# ---------------------------------------------------------------------------
def resample(pts, step):
    """Points spaced `step` pixels apart along the path (first and last kept)."""
    if len(pts) < 2:
        return list(pts)
    out = [pts[0]]
    carry = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = dist(a, b)
        if seg == 0:
            continue
        d = step - carry
        while d <= seg:
            f = d / seg
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            d += step
        carry = seg - (d - step)
    if dist(out[-1], pts[-1]) > 0.5:
        out.append(pts[-1])
    return out


def smooth(pts, passes=3):
    """Moving-average smoothing that keeps both ends where they are."""
    pts = list(pts)
    for _ in range(passes):
        if len(pts) < 5:
            break
        new = [pts[0], pts[1]]
        for i in range(2, len(pts) - 2):
            xs = [pts[j][0] for j in range(i - 2, i + 3)]
            ys = [pts[j][1] for j in range(i - 2, i + 3)]
            new.append((sum(xs) / 5, sum(ys) / 5))
        new += [pts[-2], pts[-1]]
        pts = new
    return pts


def rdp(pts, eps):
    """Ramer-Douglas-Peucker: keep only the points that matter (the corners)."""
    if len(pts) < 3:
        return list(pts)
    a, b = pts[0], pts[-1]
    best, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = line_gap(pts[i], a, b)
        if d > best:
            best, idx = d, i
    if best > eps:
        left = rdp(pts[:idx + 1], eps)
        right = rdp(pts[idx:], eps)
        return left[:-1] + right
    return [a, b]


def line_gap(p, a, b):
    """How far p is from the line through a and b."""
    seg = dist(a, b)
    if seg == 0:
        return dist(p, a)
    return abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / seg


def corner_angle(prev, p, nxt):
    """Angle in degrees at p between the directions to prev and nxt (180 = straight)."""
    a = math.atan2(prev[1] - p[1], prev[0] - p[0])
    b = math.atan2(nxt[1] - p[1], nxt[0] - p[0])
    d = abs(math.degrees(a - b)) % 360
    return 360 - d if d > 180 else d


def interpolate(poly, step, closed=False):
    """Walk along a polygon's edges, one point every `step` pixels."""
    pts = list(poly) + ([poly[0]] if closed else [])
    return resample(pts, step)


# ---------------------------------------------------------------------------
# recognizing the stroke
# ---------------------------------------------------------------------------
def recognize(points, step=6.0):
    """Returns (name, clean_points) for a finished stroke, or None if it is too small.

    name is one of: line, circle, ellipse, triangle, rectangle, square, shape, curve.
    """
    pts = [points[0]]
    for p in points[1:]:
        if dist(p, pts[-1]) >= 1.0:
            pts.append(p)
    if len(pts) < 4:
        return None
    total = path_length(pts)
    if total < 20:
        return None
    first, last = pts[0], pts[-1]
    chord = dist(first, last)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    diag = math.hypot(w, h)
    if diag < 10:
        return None

    closed = chord < 0.2 * total

    # a straight line: nothing strays far from the straight path from start to end
    if not closed:
        worst = max(line_gap(p, first, last) for p in pts)
        if worst < 0.07 * chord:
            return "line", interpolate([first, last], step)
        return "curve", smooth(resample(pts, step))

    even = resample(pts, 4.0)
    # round things first: circle or an axis-aligned ellipse
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    a, b = w / 2, h / 2
    if a > 4 and b > 4:
        err = sum(abs(math.hypot((p[0] - cx) / a, (p[1] - cy) / b) - 1) for p in even) / len(even)
        if err < 0.09:
            start_angle = math.atan2((first[1] - cy) / b, (first[0] - cx) / a)
            if abs(a - b) / max(a, b) < 0.15:
                r = (a + b) / 2
                return "circle", _ellipse_points(cx, cy, r, r, start_angle, step)
            return "ellipse", _ellipse_points(cx, cy, a, b, start_angle, step)

    # corners: triangle, rectangle...
    ring = even + [even[0]]
    corners = rdp(ring, 0.07 * diag)[:-1]
    corners = _drop_straight(corners)
    if len(corners) == 3:
        return "triangle", _closed_from(corners, first, step)
    if len(corners) == 4:
        if _axis_aligned(corners):
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            if abs((x1 - x0) - (y1 - y0)) / max(x1 - x0, y1 - y0) < 0.12:
                side = (x1 - x0 + y1 - y0) / 2
                x1, y1 = x0 + side, y0 + side
                name = "square"
            else:
                name = "rectangle"
            box = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            return name, _closed_from(box, first, step)
        return "shape", _closed_from(corners, first, step)

    # something else that loops: just make it smooth
    loop = smooth(resample(pts, step))
    return "curve", loop


def _ellipse_points(cx, cy, a, b, start, step):
    per = math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))
    n = max(24, int(per / step))
    return [(cx + a * math.cos(start + 2 * math.pi * i / n),
             cy + b * math.sin(start + 2 * math.pi * i / n)) for i in range(n + 1)]


def _drop_straight(corners):
    """Remove 'corners' that are really just a straight edge (angle near 180)."""
    pts = list(corners)
    changed = True
    while changed and len(pts) > 3:
        changed = False
        for i in range(len(pts)):
            if corner_angle(pts[i - 1], pts[i], pts[(i + 1) % len(pts)]) > 158:
                del pts[i]
                changed = True
                break
    return pts


def _axis_aligned(corners, tolerance=14):
    for i in range(len(corners)):
        a, b = corners[i], corners[(i + 1) % len(corners)]
        ang = abs(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))) % 90
        if min(ang, 90 - ang) > tolerance:
            return False
    return True


def _closed_from(corners, start, step):
    """Polygon path that begins at the corner nearest where the stroke began."""
    i = min(range(len(corners)), key=lambda k: dist(corners[k], start))
    ordered = corners[i:] + corners[:i]
    return interpolate(ordered, step, closed=True)
