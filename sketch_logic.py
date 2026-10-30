"""sketch_logic.py - the thinking behind the FIVES sketch window.

No windows or mouse in here, so every part can be tested on its own:
  Layout     where the buttons are
  View       how the page sits in the window (zoom, scroll) and the maths between screen and page
  Pen        one stroke at a time: calm the wobble, notice a hold-still and snap it to a clean shape
  Notebook   the pages (a PDF you opened, or blank ones), your ink, undo, and saving a marked-up copy

Coordinates:
  "design units" = the window's layout numbers (the window is 1280 x 800 and gets scaled to fit your screen)
  "page points"  = PDF units (a US Letter page is 612 x 792), origin at the page's top-left
"""

import datetime
import math
import os

import snap

try:
    import pymupdf                              # PyMuPDF: opens, draws and saves PDFs
except ImportError:                             # older installs call it fitz
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None

W, H = 1280, 800
VIEW_RECT = (48, 88, 1184, 600)                 # where the page is shown (x, y, w, h)

# a pen's look
INK_COLORS = [(0.24, 0.55, 1.0), (0.08, 0.14, 0.25), (0.78, 0.22, 0.18), (0.12, 0.48, 0.30)]
INK_NAMES = ["BLUE", "NAVY", "RED", "GREEN"]
DARK_INK_COLORS = [(0.30, 0.62, 1.0), (0.93, 0.95, 0.98), (1.0, 0.38, 0.38), (0.35, 0.88, 0.55)]   # how ink looks in dark mode
DARK_PAPER_RGB = (13, 20, 34)                   # dark-mode page colour: 501st navy (0-255)
DARK_INK_NAMES = ["BLUE", "WHITE", "RED", "GREEN"]
HILITE_COLOR = (1.0, 0.85, 0.2)
HILITE_ALPHA = 0.35
HILITE_WIDTH = 14.0
WIDTHS = [1.5, 2.5, 4.0, 6.0]                   # page points
ZOOMS = [1.0, 1.5, 2.0, 3.0]
ERASE_RADIUS = 9.0                              # page points
BLANK_SIZE = (612.0, 792.0)                     # US Letter


def flip_light(c):
    """Swap light and dark but keep the colour: white <-> black, light blue <-> dark blue (not orange).
    Doing it twice gives back what you started with. Used for dark mode: the saved PDF stays a normal
    white page, and the screen shows its flipped twin."""
    shift = 1.0 - max(c) - min(c)
    return tuple(min(1.0, max(0.0, v + shift)) for v in c)


def flip_light_rgb_bytes(data, w, h):
    """flip_light for a whole RGB picture (bytes, 3 per pixel). Needs numpy; returns None without it."""
    try:
        import numpy as np
    except ImportError:
        return None
    a = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3).astype(np.int16)
    shift = 255 - a.max(axis=2, keepdims=True) - a.min(axis=2, keepdims=True)
    base = np.array(DARK_PAPER_RGB, dtype=np.float32)      # black becomes 501st navy; white stays white
    out = base + np.clip(a + shift, 0, 255) * ((255 - base) / 255)
    return np.clip(out, 0, 255).astype(np.uint8).tobytes()


# ---------------------------------------------------------------------------
# where the buttons are
# ---------------------------------------------------------------------------
def _row(items, y, h, x0, gap=6):
    """Lay buttons out left to right. items: (name, width) or a number = extra gap."""
    out, x = {}, x0
    for it in items:
        if isinstance(it, (int, float)):
            x += it
            continue
        name, w = it
        out[name] = (x, y, w, h)
        x += w + gap
    return out


def _build_layout():
    rects = {}
    # top-right buttons, laid out right to left from the edge
    x = W - 48
    for name, w in (("close", 84), ("share", 84), ("save", 84), ("newpage", 100), ("open", 84)):
        x -= w
        rects[name] = (x, 36, w, 34)
        x -= 10
    tools = [("tool:ink", 70), ("tool:snap", 70), ("tool:hilite", 92), ("tool:erase", 70), 18,
             ("color:0", 36), ("color:1", 36), ("color:2", 36), ("color:3", 36), 18,
             ("width:-", 36), ("width:+", 36), 18,
             ("undo", 70), 18,
             ("prev", 40), ("next", 40), 18,
             ("zoom:-", 36), ("zoom:+", 36), ("zoom:fit", 52)]
    total = sum(it if isinstance(it, (int, float)) else it[1] + 6 for it in tools) - 6
    rects.update(_row(tools, 704, 52, (W - total) / 2))
    return rects


RECTS = _build_layout()
PILL = (RECTS["tool:ink"][0] - 8, 698, RECTS["zoom:fit"][0] + RECTS["zoom:fit"][2] - RECTS["tool:ink"][0] + 16, 64)


GRIP = (W - 60, H - 60, 60, 60)                 # bottom-right corner: drag it to grow / shrink the window
MIN_SCALE = 0.4                                 # smallest window = 40% of the design size


def hit(p):
    """What is at design point p: a button name, "grip", "page", or None (empty frame: drag to move)."""
    x, y = p
    gx, gy, gw, gh = GRIP
    if gx <= x <= gx + gw and gy <= y <= gy + gh:
        return "grip"
    for name, (rx, ry, rw, rh) in RECTS.items():
        if rx <= x <= rx + rw and ry <= y <= ry + rh:
            return name
    vx, vy, vw, vh = VIEW_RECT
    if vx <= x <= vx + vw and vy <= y <= vy + vh:
        return "page"
    return None


# ---------------------------------------------------------------------------
# moving and resizing the window (screen points, macOS style: origin at the bottom-left)
# ---------------------------------------------------------------------------
def moved_frame(start, dx, dy, screen):
    """start = (x, y, w, h) when the drag began; dx, dy = how far the pointer moved. Keeps a grab-able
    piece of the window (and its whole top edge) on screen."""
    x, y, w, h = start
    sx, sy, sw, sh = screen
    keep = 120
    nx = max(sx - w + keep, min(sx + sw - keep, x + dx))
    ny = max(sy + keep - h, min(sy + sh - h, y + dy))
    return (nx, ny, w, h)


def resized_frame(start, dx, dy, screen):
    """Drag the bottom-right corner: the top-left stays put and the window keeps its shape."""
    x, y, w, h = start
    sx, sy, sw, sh = screen
    want_w = ((w + dx) + (h - dy) * W / H) / 2      # average of "follow the pointer across" and "down"
    top = y + h
    biggest = min(sw, sh * W / H, (sx + sw - x), (top - sy) * W / H)
    nw = max(W * MIN_SCALE, min(biggest, want_w))
    nh = nw * H / W
    return (x, top - nh, nw, nh)


def quartz_frame(frame, main_h):
    """Turn a bottom-left-origin frame into the top-left-origin one the mouse events use."""
    x, y, w, h = frame
    return (x, main_h - (y + h), w, h)


# ---------------------------------------------------------------------------
# the page in the window
# ---------------------------------------------------------------------------
class View:
    """Zoom, scroll, and the maths between design units and page points."""

    def __init__(self, page_w=BLANK_SIZE[0], page_h=BLANK_SIZE[1]):
        self.set_page(page_w, page_h)

    def set_page(self, page_w, page_h):
        self.pw, self.ph = page_w, page_h
        self.zoom_i = 0
        self.to_top()

    @property
    def scale(self):
        """Design units per page point. Zoom 1x = the page is as wide as the view; scroll for the rest."""
        vx, vy, vw, vh = VIEW_RECT
        return vw / self.pw * ZOOMS[self.zoom_i]

    def to_top(self):
        """Centred left-right, showing the top of the page."""
        self.pan = [0.0, 0.0]
        self.pan[1] = self._limits()[1]

    def _limits(self):
        vx, vy, vw, vh = VIEW_RECT
        s = self.scale
        return (max(0.0, (self.pw * s - vw) / 2), max(0.0, (self.ph * s - vh) / 2))

    def clamp(self):
        lx, ly = self._limits()
        self.pan[0] = max(-lx, min(lx, self.pan[0]))
        self.pan[1] = max(-ly, min(ly, self.pan[1]))

    def origin(self):
        """Top-left of the page, in design units."""
        self.clamp()
        vx, vy, vw, vh = VIEW_RECT
        s = self.scale
        return (vx + (vw - self.pw * s) / 2 + self.pan[0], vy + (vh - self.ph * s) / 2 + self.pan[1])

    def to_page(self, p):
        ox, oy = self.origin()
        s = self.scale
        return ((p[0] - ox) / s, (p[1] - oy) / s)

    def to_view(self, q):
        ox, oy = self.origin()
        s = self.scale
        return (ox + q[0] * s, oy + q[1] * s)

    def zoom_by(self, step):
        self.zoom_i = max(0, min(len(ZOOMS) - 1, self.zoom_i + step))
        self.clamp()

    def zoom_fit(self):
        self.zoom_i = 0
        self.to_top()

    def scroll(self, dx, dy):
        self.pan[0] += dx
        self.pan[1] += dy
        self.clamp()


# ---------------------------------------------------------------------------
# strokes and the pen
# ---------------------------------------------------------------------------
class Stroke:
    __slots__ = ("pts", "color", "width", "alpha")

    def __init__(self, pts, color, width, alpha=1.0):
        self.pts, self.color, self.width, self.alpha = pts, color, width, alpha


class Pen:
    """One stroke at a time. Positions in, a calm (and maybe snapped) stroke out.

    Positions are design units while drawing (so the hold-still pixel sizes feel the same
    whatever the zoom); end() converts the finished stroke to page points.
    """

    def __init__(self, hold_seconds=0.1, hold_radius=8.0, min_length=60.0, smooth_passes=2, live_follow=0.6):
        self.hold_seconds, self.hold_radius, self.min_length = hold_seconds, hold_radius, min_length
        self.smooth_passes = smooth_passes
        self.live_follow = live_follow           # 1 = ink goes exactly where you point, lower = calmer
        self.active = False
        self.enabled = True                      # may a hold-still snap right now? (the window flips this live)
        self.snapped = None                      # name of the shape once snapped ("circle"...)

    def begin(self, t, p, snapping):
        """snapping = this kind of stroke CAN snap (pen, not highlighter). Whether it does is `enabled`, checked at hold time."""
        self.active = True
        self.locked = False                      # after a snap, ignore the rest of this stroke
        self.snapped = None
        self.path = None
        self.raw = [p]
        self.live = [p]
        self.snapper = snap.Snapper(self.hold_seconds, self.hold_radius, self.min_length) if snapping else None
        if self.snapper:
            self.snapper.add(t, p)

    def move(self, t, p):
        if not self.active or self.locked:
            return
        self.raw.append(p)
        last = self.live[-1]
        k = self.live_follow
        q = (last[0] + k * (p[0] - last[0]), last[1] + k * (p[1] - last[1]))
        self.live.append(q)
        if self.snapper:
            self.snapper.add(t, q)

    def tick(self, t):
        """Call often while the pen is down (even when nothing moves). Returns the shape name the moment it snaps."""
        if not self.active or self.locked or self.snapper is None:
            return None
        self.snapper.add(t, self.live[-1])
        if not self.enabled or not self.snapper.ready(t):
            return None
        result = snap.recognize(self.snapper.stroke(), 4.0)
        if result is None:
            self.snapper.rearm(t)
            return None
        self.snapped, self.path = result
        self.locked = True
        return self.snapped

    def shown(self):
        """The points to draw right now (design units)."""
        if not self.active:
            return []
        return self.path if self.path is not None else self.live

    def end(self, to_page):
        """Pen up. Returns the finished points in page points, or None if there was nothing."""
        if not self.active:
            return None
        self.active = False
        if self.path is not None:
            pts = self.path
        elif len(self.live) < 3:
            p = self.live[-1]
            pts = [p, (p[0] + 0.01, p[1])]                         # a tap = a dot
        else:
            pts = snap.smooth(snap.resample(self.live, 1.5), self.smooth_passes)
        return [to_page(p) for p in pts]


# ---------------------------------------------------------------------------
# the notebook: pages + ink + saving
# ---------------------------------------------------------------------------
def _dist_to_segment(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    seg = dx * dx + dy * dy
    t = 0.0 if seg == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / seg))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def stroke_touches(stroke, p, radius):
    pts = stroke.pts
    if len(pts) == 1:
        return math.hypot(p[0] - pts[0][0], p[1] - pts[0][1]) <= radius + stroke.width / 2
    reach = radius + stroke.width / 2
    return any(_dist_to_segment(p, pts[i], pts[i + 1]) <= reach for i in range(len(pts) - 1))


class Notebook:
    def __init__(self, folder):
        if pymupdf is None:
            raise RuntimeError("PyMuPDF is missing. Run:  pip install pymupdf")
        self.folder = os.path.expanduser(folder)
        self.cache = {}
        self.version = 0                        # goes up whenever the page pictures must be redrawn
        self.new_blank()

    def _reset_cache(self):
        self.cache.clear()
        self.version += 1

    # -- starting points ------------------------------------------------------
    def new_blank(self):
        self.doc = pymupdf.open()
        self.doc.new_page(width=BLANK_SIZE[0], height=BLANK_SIZE[1])
        self.strokes = [[]]
        self.ops = []                           # undo history
        self.source = None
        stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
        self.out_path = os.path.join(self.folder, f"FIVES-Notes-{stamp}.pdf")
        self.dirty = False
        self._reset_cache()

    def open_pdf(self, path):
        """Open a PDF you were given. Your original is never changed; saving writes a copy beside it in the notes folder."""
        path = os.path.expanduser(path)
        doc = pymupdf.open(path)
        if doc.needs_pass:
            doc.close()
            raise ValueError("that PDF is password protected")
        if doc.page_count == 0:
            doc.close()
            raise ValueError("that PDF has no pages")
        self.doc = doc
        self.strokes = [[] for _ in range(doc.page_count)]
        self.ops = []
        self.source = path
        stem = os.path.splitext(os.path.basename(path))[0]
        self.out_path = os.path.join(self.folder, f"{stem}-marked.pdf")
        self.dirty = False
        self._reset_cache()

    # -- pages ------------------------------------------------------------------
    @property
    def count(self):
        return self.doc.page_count

    def page_size(self, i):
        r = self.doc[i].rect
        return (r.width, r.height)

    def render(self, i, px_per_point, dark=False):
        """The page as a PNG (bytes) at that many pixels per point. Cached.
        dark=True: light and dark swapped for the screen (the PDF itself is never changed)."""
        key = (i, round(px_per_point, 2), dark)
        if key not in self.cache:
            if len(self.cache) > 8:
                self.cache.pop(next(iter(self.cache)))
            pix = self.doc[i].get_pixmap(matrix=pymupdf.Matrix(px_per_point, px_per_point), alpha=False)
            if dark:
                pix = _dark_pixmap(pix)
            self.cache[key] = pix.tobytes("png")
        return self.cache[key]

    def add_page_after(self, i):
        """A blank page right after page i, the same size as it. Returns the new page's number."""
        w, h = self.page_size(i)
        self.doc.new_page(pno=i + 1, width=w, height=h)
        self.strokes.insert(i + 1, [])
        for op in self.ops:                     # undo entries after this page now point one page later
            if op[1] > i:
                op[1] += 1
        self._reset_cache()
        self.dirty = True
        return i + 1

    # -- ink -----------------------------------------------------------------------
    def add_stroke(self, i, stroke):
        self.strokes[i].append(stroke)
        self.ops.append(["add", i, stroke])
        self.dirty = True

    def erase_at(self, i, p, radius=ERASE_RADIUS):
        hits = [(k, s) for k, s in enumerate(self.strokes[i]) if stroke_touches(s, p, radius)]
        if not hits:
            return 0
        for k, s in reversed(hits):
            del self.strokes[i][k]
        self.ops.append(["erase", i, hits])
        self.dirty = True
        return len(hits)

    def undo(self):
        """Take back the last thing. Returns the page it happened on (or None)."""
        if not self.ops:
            return None
        kind, i, data = self.ops.pop()
        if kind == "add":
            if data in self.strokes[i]:
                self.strokes[i].remove(data)
        else:
            for k, s in data:
                self.strokes[i].insert(min(k, len(self.strokes[i])), s)
        self.dirty = True
        return i

    # -- saving ----------------------------------------------------------------------
    def save(self, path=None):
        """Write a marked-up copy as a PDF. The ink is drawn onto a copy, so you can keep editing and save again."""
        path = os.path.expanduser(path or self.out_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if self.source and os.path.abspath(path) == os.path.abspath(self.source):
            raise ValueError("won't overwrite your original PDF")
        out = pymupdf.open("pdf", self.doc.tobytes())
        for i, strokes in enumerate(self.strokes):
            if not strokes:
                continue
            page = out[i]
            fix = page.derotation_matrix            # pages that are stored rotated
            shape = page.new_shape()
            for s in strokes:
                pts = [pymupdf.Point(*p) * fix for p in s.pts]
                if len(pts) == 1:
                    pts = [pts[0], pymupdf.Point(pts[0].x + 0.01, pts[0].y)]
                shape.draw_polyline(pts)
                shape.finish(color=s.color, fill=None, width=s.width, closePath=False,
                             stroke_opacity=s.alpha, lineCap=1, lineJoin=1)
            shape.commit()
        out.save(path, garbage=3, deflate=True)
        out.close()
        self.dirty = False
        self.out_path = path
        return path


def _dark_pixmap(pix):
    """A page picture with light and dark swapped, colours kept."""
    try:
        if pix.n == 3 and pix.stride == pix.width * 3:
            out = flip_light_rgb_bytes(pix.samples, pix.width, pix.height)
            if out is not None:
                return pymupdf.Pixmap(pymupdf.csRGB, pix.width, pix.height, out, 0)
    except Exception as e:
        print("sketch: dark page fallback:", e)
    pix.invert_irect()                          # plain invert: colours shift, but still dark
    return pix
