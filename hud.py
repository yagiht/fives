"""
hud.py - the "visor" look for the eyes window.

Instead of showing the plain camera picture, we draw a heads-up display:
  - an angled six-sided visor frame (like a clone trooper helmet view)
  - a viewport in the middle showing YOU (natural colors with a cool blue tint, or a full blue
    hologram), or just your hand wireframe on a dark grid ("hand only")
  - your hand's wiring, a bracket around the cursor spot, and readouts on the sides

Keys (in the eyes window):  H = camera / hand-only view    [ and ] = less / more blue tint    T = hologram on / off

Why two sizes: every position in this file is in "layout units" (the window is 1280 x 720 units).
We actually draw at SCALE times that many pixels (2 = double). On a Retina screen the window is
shown at 2 pixels per unit, so drawing at 2x makes text and lines razor sharp instead of
blurry-grainy from the Mac stretching a small picture.

How it stays fast: everything that never changes (the frame, rulers, labels, the dark area
outside the visor) is drawn ONCE into a "chrome" picture and stamped on top of every frame.
Only the moving parts (the camera, your hand, the bracket, the numbers) are drawn each frame.
"""

import os

import cv2
import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
    _DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    _FONT_MEDIUM = os.path.join(_DIR, "Rajdhani-Medium.ttf")
    _FONT_BOLD = os.path.join(_DIR, "Rajdhani-Bold.ttf")
    ImageFont.truetype(_FONT_MEDIUM, 12)
    ImageFont.truetype(_FONT_BOLD, 12)
    _HAVE_FONT = True
except Exception:                      # no Pillow or no font files: use OpenCV's plain font
    _HAVE_FONT = False

# Colors are (Blue, Green, Red) in OpenCV.
BLUE = (255, 139, 61)        # 501st blue  #3d8bff
PALE = (255, 192, 156)       # pale blue    #9cc0ff
WHITE = (242, 237, 233)      # off-white    #e9edf2
GREY = (168, 151, 140)       # quiet labels #8c97a8
DIM = (64, 49, 42)           # dim lines    #2a3140
DARK = (16, 10, 7)           # visor dark   #070a10
OUTSIDE = (10, 6, 4)         # outside the visor
GREEN = (156, 255, 61)       # hand found   #3dff9c
RED = (94, 77, 255)          # no hand

FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_BOLD = cv2.FONT_HERSHEY_DUPLEX

HAND_BONES = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]
FINGERTIPS = (4, 12, 16, 20)       # index tip (8) gets its own bright dot
MODES = ["POINT", "CLICK", "DRAG", "SCROLL", "DRAW"]


def mode_of(state: str, draw_on: bool):
    """Turn the eyes.py state ("", PINCH, DRAG, DRAWING, ...) into (mode, little note)."""
    if state.startswith("SCROLL"):
        return "SCROLL", "TOUCH" if state == "SCROLLING" else ""
    if state.startswith("DRAW") or draw_on:
        return "DRAW", "INK" if state == "DRAWING" else ""
    if state == "DRAG":
        return "DRAG", ""
    if state in ("PINCH", "PRESSED", "RIGHT"):
        return "CLICK", {"PINCH": "HOLD", "PRESSED": "DOWN", "RIGHT": "RIGHT"}[state]
    return "POINT", ""


class Pen:
    """Drawing helpers that take LAYOUT units and draw at k times the pixels."""

    def __init__(self, k):
        self.k = k

    def p(self, pt):
        return int(round(pt[0] * self.k)), int(round(pt[1] * self.k))

    def t(self, thick):
        return thick if thick < 0 else max(1, int(round(thick * self.k)))

    def pts(self, arr):
        return np.round(np.asarray(arr, np.float64) * self.k).astype(np.int32)

    def line(self, img, a, b, color, thick=1):
        cv2.line(img, self.p(a), self.p(b), color, self.t(thick), cv2.LINE_AA)

    def circle(self, img, c, r, color, thick=1):
        cv2.circle(img, self.p(c), int(round(r * self.k)), color, self.t(thick), cv2.LINE_AA)

    def rect(self, img, a, b, color, thick=1):
        cv2.rectangle(img, self.p(a), self.p(b), color, self.t(thick), cv2.LINE_AA)

    def poly(self, img, pts, color, thick=1):
        cv2.polylines(img, [self.pts(pts)], True, color, self.t(thick), cv2.LINE_AA)

    def fill(self, img, pts, color):
        cv2.fillPoly(img, [self.pts(pts)], color, cv2.LINE_AA)

    def arc(self, img, c, r, start, end, color, thick=1):
        cv2.ellipse(img, self.p(c), (int(round(r * self.k)),) * 2, 0, start, end, color, self.t(thick), cv2.LINE_AA)

    def arrow(self, img, a, b, color, thick=1, tip=0.4):
        cv2.arrowedLine(img, self.p(a), self.p(b), color, self.t(thick), cv2.LINE_AA, tipLength=tip)

    # -- text: a squared, techy font (Rajdhani) drawn with Pillow; falls back to OpenCV's plain font --
    _fonts = {}
    _masks = {}

    @classmethod
    def _font(cls, bold, px):
        key = (bold, px)
        if key not in cls._fonts:
            cls._fonts[key] = ImageFont.truetype(_FONT_BOLD if bold else _FONT_MEDIUM, px)
        return cls._fonts[key]

    def _mask(self, s, scale, bold, spacing):
        """A grey picture of the text (255 = ink), made once and remembered."""
        key = (s, scale, bold, spacing, self.k)
        m = self._masks.get(key)
        if m is None:
            px = max(6, int(round(scale * 34 * self.k)))      # 34 ~ matches the old letters' height
            f = self._font(bold, px)
            gap = spacing * self.k
            asc, desc = f.getmetrics()
            width = int(sum(f.getlength(c) for c in s) + gap * max(len(s) - 1, 0)) + 4
            im = Image.new("L", (width, asc + desc + 2), 0)
            dr = ImageDraw.Draw(im)
            x = 0.0
            for c in s:
                dr.text((x, 0), c, font=f, fill=255)
                x += f.getlength(c) + gap
            m = (np.asarray(im), asc)
            if len(self._masks) > 600:
                self._masks.clear()
            self._masks[key] = m
        return m

    def text(self, img, s, org, scale=0.45, color=WHITE, thick=1, spacing=2, font=FONT, right=False):
        """Write text with extra space between letters (looks more like a HUD).
        right=True: org is the RIGHT end of the text. Returns the x (layout units) where it ended."""
        k = self.k
        if not _HAVE_FONT:
            return self._text_cv(img, s, org, scale, color, thick, spacing, font, right)
        bold = font == FONT_BOLD or thick >= 2
        mask, asc = self._mask(s, scale, bold, spacing)
        mh, mw = mask.shape
        x = int(round(org[0] * k)) - (mw - 4 if right else 0)
        y = int(round(org[1] * k)) - asc                     # org is the text baseline
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + mw, img.shape[1]), min(y + mh, img.shape[0])
        if x1 > x0 and y1 > y0:
            a = mask[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.uint16)[..., None]
            roi = img[y0:y1, x0:x1]
            col = np.array(color, np.uint16)
            roi[:] = ((roi.astype(np.uint16) * (255 - a) + col * a) // 255).astype(np.uint8)
        return (x + mw - 4) / k if not right else org[0]

    def _text_cv(self, img, s, org, scale, color, thick, spacing, font, right):
        k = self.k
        widths = [cv2.getTextSize(ch, font, scale * k, self.t(thick))[0][0] for ch in s]
        total = sum(widths) + spacing * k * max(len(s) - 1, 0)
        x, y = org[0] * k, org[1] * k
        if right:
            x -= total
        for ch, w in zip(s, widths):
            if ch != " ":
                cv2.putText(img, ch, (int(round(x)), int(round(y))), font, scale * k, color, self.t(thick), cv2.LINE_AA)
            x += w + spacing * k
        return x / k

    def text_width(self, s, scale=0.45, thick=1, spacing=2, font=FONT):
        k = self.k
        if _HAVE_FONT:
            return (self._mask(s, scale, font == FONT_BOLD or thick >= 2, spacing)[0].shape[1] - 4) / k
        w = sum(cv2.getTextSize(ch, font, scale * k, self.t(thick))[0][0] for ch in s)
        return (w + spacing * k * max(len(s) - 1, 0)) / k


class Hud:
    """Window layout (in layout units, default 1280 x 720):

        +------------------- visor frame (angled, six sides) -------------------+
        |  status        [ FIVES  EYES ]                        telemetry        |
        |  mode list    +-------------------------------+                       |
        |               |   VIEWPORT: you (or hand)     |       (notch)          |
        |  pinch gap    |   + wiring + bracket          |       switches         |
        |               +-------------------------------+                       |
        |                     key legend                                         |
        +------------------------------------------------------------------------+
    Only the viewport shows the camera. Everything else is the visor's dark panel.
    """

    def __init__(self, width=1280, height=720, view="cam", glow=True, scale=2,
                 strength=0.35, denoise=0.2):
        self.W, self.H = width, height          # layout units = the size the window is shown at
        self.k = max(1, int(scale))
        self.d = Pen(self.k)
        self.view = "hand" if view == "hand" else "cam"
        self.glow = glow
        self.strength = float(min(1.0, max(0.0, strength)))   # 0 = natural color, 1 = full blue hologram
        self.denoise = float(min(0.6, max(0.0, denoise)))     # blend with the previous picture: calms sensor noise
        self._key = None                        # (camera width, camera height) the caches were built for
        self._prev = None
        self._holo_lut = self._make_lut()
        self._tint_lut = self._make_tint()

    @property
    def size(self):
        """The size to show the window at (layout units)."""
        return self.W, self.H

    def toggle(self) -> str:
        self.view = "hand" if self.view == "cam" else "cam"
        return self.view

    def toggle_holo(self) -> float:
        """Hologram on/off: 0 = plain cool-graded camera, back again = your last blue amount."""
        if self.strength > 0.01:
            self._last_strength, self.strength = self.strength, 0.0
        else:
            self.strength = getattr(self, "_last_strength", 0.35) or 0.35
        return self.strength

    def nudge(self, amount: float) -> float:
        self.strength = float(min(1.0, max(0.0, round(self.strength + amount, 2))))
        return self.strength

    # -- one-time pictures --------------------------------------------------
    @staticmethod
    def _make_lut():
        """Brightness -> color: black -> deep blue -> 501st blue -> almost white."""
        stops = [(0.0, (8, 5, 3)), (0.35, (120, 55, 18)), (0.7, BLUE), (1.0, (255, 238, 222))]
        lut = np.zeros((256, 1, 3), np.uint8)
        for i in range(256):
            t = (i / 255.0) ** 1.1
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t <= t1:
                    k = (t - t0) / (t1 - t0)
                    lut[i, 0] = [int(a + (b - a) * k) for a, b in zip(c0, c1)]
                    break
        return lut

    @staticmethod
    def _make_tint():
        """A gentle cool grade for the natural-color picture: a touch less red, a touch more blue."""
        x = np.arange(256, dtype=np.float32) / 255.0
        lut = np.zeros((256, 1, 3), np.uint8)
        for ch, gain in ((0, 1.00), (1, 0.97), (2, 0.90)):          # B, G, R
            lut[:, 0, ch] = np.clip((x ** 0.95) * gain * 255 * 0.96 + 4, 0, 255)
        return lut

    def _hex(self, inset):
        W, H, m = self.W, self.H, self.m + inset
        slant = (W - 2 * self.m) * 0.07
        return [(m + slant, m), (W - m - slant, m), (W - m, H / 2),
                (W - m - slant, H - m), (m + slant, H - m), (m, H / 2)]

    def _viewport_poly(self, grow=0):
        x0, y0, x1, y1 = self.vx0 - grow, self.vy0 - grow, self.vx0 + self.vw + grow, self.vy0 + self.vh + grow
        c = 34 + grow / 2                                    # the cut-off corners
        return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c),
                (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]

    def _build(self, fw, fh):
        """Draw everything that never moves, once (and again if the camera size changes)."""
        W, H, k, d = self.W, self.H, self.k, self.d
        self._key = (fw, fh)
        self._prev = None
        self.m = m = W * 0.02

        # the viewport: as big as fits between the side panels, same shape as the camera picture
        top, bottom, max_w = H * 0.14, H * 0.87, W * 0.54
        vh = bottom - top
        vw = vh * fw / fh
        if vw > max_w:
            vw, vh = max_w, max_w * fh / fw
        self.vw, self.vh = int(round(vw)), int(round(vh))
        self.vx0 = int(round((W - self.vw) / 2))
        self.vy0 = int(round(top + (bottom - top - self.vh) / 2))
        self.dvw, self.dvh = self.vw * k, self.vh * k       # viewport size in real pixels
        self.dvx0, self.dvy0 = self.vx0 * k, self.vy0 * k

        # the visor's panel material: dark blue-black with a soft glow in the middle and a faint grid
        yy, xx = np.mgrid[0:H // 2, 0:W // 2].astype(np.float32)
        dist = np.sqrt(((xx - W / 4) / (W * 0.3)) ** 2 + ((yy - H / 4) / (H * 0.35)) ** 2)
        kk = np.clip(1 - dist, 0, 1)[:, :, None]
        center, edge = np.array([30, 19, 12], np.float32), np.array(DARK, np.float32)
        base = (edge + (center - edge) * kk).astype(np.uint8)
        chrome = cv2.resize(base, (W * k, H * k), interpolation=cv2.INTER_CUBIC)
        grid = np.array([22, 12, 5], np.uint8)
        step = 32 * k
        for y in range(0, H * k, step):
            chrome[y] = cv2.add(chrome[y], grid)
        for x in range(0, W * k, step):
            chrome[:, x] = cv2.add(chrome[:, x], grid)
        mask = np.full((H * k, W * k), 255, np.uint8)
        cv2.fillPoly(mask, [d.pts(self._viewport_poly())], 0, cv2.LINE_AA)   # the viewport is the only see-through part

        # outside the visor: black. The visor's double outline.
        outer, inner = self._hex(0), self._hex(14)
        inside = np.zeros((H * k, W * k), np.uint8)
        cv2.fillPoly(inside, [d.pts(outer)], 255)
        chrome[inside == 0] = OUTSIDE
        d.poly(chrome, outer, BLUE, 3)
        d.poly(chrome, inner, (150, 82, 36), 1)

        # viewport frame: a bright edge, a dim outer edge, white accents on the cut corners
        d.poly(chrome, self._viewport_poly(10), DIM, 1)
        d.poly(chrome, self._viewport_poly(2), BLUE, 2)
        x0, y0, x1, y1 = self.vx0 - 2, self.vy0 - 2, self.vx0 + self.vw + 2, self.vy0 + self.vh + 2
        c = 35
        for a, b in (((x0, y0 + c), (x0 + c, y0)), ((x1 - c, y0), (x1, y0 + c)),
                     ((x1, y1 - c), (x1 - c, y1)), ((x0 + c, y1), (x0, y1 - c))):
            d.line(chrome, a, b, WHITE, 3)
        # tick scales down both sides of the viewport, and a center mark on each side
        for y in range(self.vy0 + c + 10, self.vy0 + self.vh - c - 5, 15):
            long = (y - self.vy0) % 75 < 15
            d.line(chrome, (x0 - 16, y), (x0 - (26 if long else 21), y), GREY if long else DIM, 1)
            d.line(chrome, (x1 + 16, y), (x1 + (26 if long else 21), y), GREY if long else DIM, 1)
        for x in (x0 - 10, x1 + 10):
            d.line(chrome, (x, self.vy0 + self.vh / 2 - 14), (x, self.vy0 + self.vh / 2 + 14), BLUE, 3)

        # tick rulers at the top and bottom of the visor
        rx0, rx1 = int(W * 0.36), int(W * 0.64)
        for x in range(rx0, rx1 + 1, 10):
            tall = (x - rx0) % 50 == 0
            d.line(chrome, (x, m + 4), (x, m + (16 if tall else 9)), WHITE if tall else GREY, 1)
            if abs(x - W // 2) > 24:
                d.line(chrome, (x, H - m - 4), (x, H - m - 9), GREY, 1)
        d.fill(chrome, [(W / 2 - 9, H - m - 4), (W / 2 + 9, H - m - 4), (W / 2, H - m - 17)], WHITE)

        # the arrow-shaped notch on the right edge (from the reference picture) and a matching one on the left
        nx = W - m - 74
        d.fill(chrome, [(nx + 44, H / 2 - 26), (nx + 44, H / 2 + 26), (nx, H / 2)], (110, 60, 26))
        for i, col in enumerate((WHITE, BLUE, BLUE)):
            d.circle(chrome, (nx + 16 + i * 9, H / 2), 3, col, -1)
        lnx = m + 52
        d.fill(chrome, [(lnx - 30, H / 2 - 20), (lnx - 30, H / 2 + 20), (lnx, H / 2)], (110, 60, 26))

        # --- labels that never change go into the chrome too ---
        lx = int(W * 0.075)
        self.lx, self.col_w = lx, self.vx0 - 40 - lx
        self.rx = W - int(W * 0.075)
        self.my, self.gy, self.ry, self.sy = int(H * 0.32), int(H * 0.66), int(H * 0.19), int(H * 0.64)
        my, ry = self.my, self.ry
        e = d.text(chrome, "MODE", (lx, my - 6), 0.36, GREY, 1, 3)
        d.line(chrome, (e + 8, my - 10), (lx + self.col_w, my - 10), GREY, 1)
        for i, name in enumerate(MODES):
            y = my + 8 + i * 30
            d.line(chrome, (lx, y), (lx, y + 25), DIM, 2)
        d.text(chrome, "PINCH GAP", (lx, self.gy - 8), 0.34, GREY, 1, 3)
        d.text(chrome, "TELEMETRY", (self.rx, ry - 4), 0.34, GREY, 1, 3, right=True)
        d.text(chrome, "FPS", (self.rx - 52, ry + 34), 0.36, GREY, 1, 3, right=True)

        label = "FIVES  EYES"
        tw = d.text_width(label, 0.5, 1, 4, FONT_BOLD)
        tx, ty = W / 2 - tw / 2, m + 46
        d.rect(chrome, (tx - 26, ty - 20), (tx + tw + 26, ty + 9), DARK, -1)
        d.rect(chrome, (tx - 26, ty - 20), (tx + tw + 26, ty + 9), BLUE, 1)
        d.rect(chrome, (tx + tw + 11, ty - 9), (tx + tw + 16, ty - 4), BLUE, -1)
        d.text(chrome, label, (tx, ty), 0.5, WHITE, 1, 4, FONT_BOLD)
        self.title_dot = (tx - 16, ty - 9)

        keys = [("CMD+SHIFT", "SCROLL"), ("CMD+ESC", "DRAW"), ("OPT", "INK"),
                ("C", "CURSOR"), ("H", "VIEW"), ("T", "HOLO"), ("[ ]", "TINT"), ("Q", "QUIT")]
        pieces = [(a, b, d.text_width(a, 0.36, 1, 1) + 8 + d.text_width(b, 0.34, 1, 2) + 20) for a, b in keys]
        total = sum(p[2] for p in pieces) + 6 * (len(pieces) - 1)
        x, y = W / 2 - total / 2, H - m - 32
        for a, b, w in pieces:
            d.rect(chrome, (x, y - 16), (x + w, y + 8), DARK, -1)
            d.rect(chrome, (x, y - 16), (x + w, y + 8), DIM, 1)
            e = d.text(chrome, a, (x + 10, y), 0.36, WHITE, 1, 1)
            d.text(chrome, b, (e + 8, y), 0.34, GREY, 1, 2)
            x += w + 6

        self._chrome = chrome
        self._out = chrome.copy()            # the picture we draw into every frame (never re-allocated)
        vx1 = self.vx0 + self.vw
        self._dyn = [                        # (x0, y0, x1, y1) in real pixels: the panels whose text changes
            (int((lx - 14) * k), int((H * 0.19 - 24) * k), int((self.vx0 - 30) * k), int((H * 0.80) * k)),
            (int(max(self.rx - 200, vx1 + 30) * k), int((ry - 22) * k), int((self.rx + 14) * k), int((self.sy + 3 * 22 + 4) * k)),
        ]
        roi = (slice(self.dvy0, self.dvy0 + self.dvh), slice(self.dvx0, self.dvx0 + self.dvw))
        self._roi = roi
        self._chrome_roi = np.ascontiguousarray(chrome[roi])
        self._mask_roi = np.ascontiguousarray(mask[roi])    # 255 on the visor frame, 0 where the picture shows

        # viewport background for "hand only": a soft glow and a grid
        yy, xx = np.mgrid[0:self.dvh, 0:self.dvw].astype(np.float32)
        dist = np.sqrt(((xx - self.dvw / 2) / (self.dvw * 0.6)) ** 2 + ((yy - self.dvh / 2) / (self.dvh * 0.65)) ** 2)
        kk = np.clip(1 - dist, 0, 1)[:, :, None]
        bg = (np.array(DARK, np.float32) + (np.array([48, 28, 15], np.float32) - np.array(DARK, np.float32)) * kk).astype(np.uint8)
        gstep = 35 * k
        bg[::gstep, :] = (70, 40, 18)
        bg[:, ::gstep] = (70, 40, 18)
        self._hand_bg = bg

        # scan lines: a darker row now and then (a thin, soft texture that doesn't eat detail)
        self._scan_rows = slice(0, self.dvh, 3 * k)
        self._ramp = np.linspace(0.45, 0.0, self.col_w * k).astype(np.float32)    # the lit-row glow
        self._blue = np.array(BLUE, np.float32)

    # -- every frame --------------------------------------------------------
    def _camera(self, frame):
        """The picture for the viewport: calm the noise, grade the color, add glow."""
        dw, dh = self.dvw, self.dvh
        if self.denoise > 0 and self._prev is not None and self._prev.shape == frame.shape:
            frame = cv2.addWeighted(frame, 1 - self.denoise, self._prev, self.denoise, 0)
        self._prev = frame
        fh, fw = frame.shape[:2]
        interp = cv2.INTER_AREA if dw < fw else cv2.INTER_CUBIC
        color = cv2.resize(frame, (dw, dh), interpolation=interp)
        s = self.strength
        if s < 0.99:
            color = cv2.LUT(color, self._tint_lut)
        if s > 0.01:
            gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
            holo = cv2.LUT(cv2.merge([gray, gray, gray]), self._holo_lut)
            if self.glow:                                    # bright outlines, strong edges only (not noise)
                small = cv2.resize(gray, (dw // 2, dh // 2), interpolation=cv2.INTER_AREA)
                edges = cv2.Canny(cv2.GaussianBlur(small, (5, 5), 0), 60, 150)
                edges = cv2.GaussianBlur(edges, (0, 0), 1.0)
                edges = cv2.resize(edges, (dw, dh), interpolation=cv2.INTER_LINEAR)
                holo = cv2.add(holo, cv2.merge([edges // 3, edges // 4, edges // 6]))
            color = holo if s >= 0.99 else cv2.addWeighted(color, 1 - s, holo, s, 0)
        return color

    def render(self, frame, points, aim, state, progress, info):
        """frame: the (mirrored) camera picture. points: 21 (x, y) in 0..1, or None.
        aim: cursor spot in 0..1 or None. info: dict with fps, detect_ms, lag_ms,
        cursor_on, draw_on, gap. Returns the picture to show (k times the layout size)."""
        fh, fw = frame.shape[:2]
        if self._key != (fw, fh):
            self._build(fw, fh)
        W, H, k, d = self.W, self.H, self.k, self.d
        cam = self.view == "cam"
        found = points is not None

        def to_px(p):                                        # camera 0..1 -> layout units INSIDE the viewport picture
            return p[0] * self.vw, p[1] * self.vh

        out = self._out
        for x0, y0, x1, y1 in self._dyn:                     # wipe just the text panels
            out[y0:y1, x0:x1] = self._chrome[y0:y1, x0:x1]
        view = self._camera(frame) if cam else self._hand_bg.copy()
        rows = view[self._scan_rows]
        rows -= rows >> 2                                    # those rows: 75% brightness

        # --- the hand: drawn onto the viewport picture itself, so nothing can land outside it ---
        if found:
            px = [to_px(p) for p in points]
            for a, b in HAND_BONES:
                d.line(view, px[a], px[b], WHITE, 2)
            for a, b in ((6, 7), (7, 8), (3, 4)):
                d.line(view, px[a], px[b], BLUE, 3)
            for i, p in enumerate(px):
                if i in FINGERTIPS:
                    d.circle(view, p, 6, BLUE, -1)
                elif i != 8:
                    d.circle(view, p, 4, WHITE, -1)
            d.circle(view, px[8], 7, (255, 255, 255), -1)
            tip = px[8]
            d.text(view, f"X {points[8][0]:.2f}  Y {points[8][1]:.2f}", (tip[0] + 50, tip[1] - 34), 0.34, PALE, 1, 1)
        if found and aim is not None:
            self._bracket(view, to_px(aim), state, progress)

        out[self._roi] = view
        out_roi = out[self._roi]                              # the cut-off corners belong to the visor frame
        cv2.copyTo(self._chrome_roi, self._mask_roi, out_roi)

        # --- title dot (red while draw mode is on) ---
        tx, ty = self.title_dot
        d.rect(out, (tx, ty), (tx + 5, ty + 5), RED if info.get("draw_on") else BLUE, -1)

        # --- left column ---
        lx, col_w, my = self.lx, self.col_w, self.my
        ly = int(H * 0.19)
        d.circle(out, (lx + 4, ly - 5), 5, GREEN if found else RED, -1)
        d.text(out, "HAND LOCK" if found else "NO HAND", (lx + 18, ly), 0.42, WHITE, 1, 3)
        for i in range(5):
            d.rect(out, (lx + 18 + i * 18, ly + 8), (lx + 32 + i * 18, ly + 13), BLUE if found else DIM, -1)

        mode, note = mode_of(state, info.get("draw_on", False))
        for i, name in enumerate(MODES):
            y = my + 8 + i * 30
            if name != mode:
                d.text(out, f"0{i + 1}", (lx + 10, y + 18), 0.34, GREY, 1, 1)
                d.text(out, name, (lx + 36, y + 18), 0.46, GREY, 1, 3)
                continue
            y0, y1, x0, x1 = y * k, (y + 26) * k, lx * k, (lx + col_w) * k
            roi = out[y0:y1, x0:x1]
            ramp = self._ramp[None, :, None]
            out[y0:y1, x0:x1] = np.clip(roi + ramp * self._blue, 0, 255).astype(np.uint8)
            d.line(out, (lx, y), (lx, y + 25), BLUE, 2)
            d.text(out, f"0{i + 1}", (lx + 10, y + 18), 0.34, PALE, 1, 1)
            end = d.text(out, name, (lx + 36, y + 18), 0.46, WHITE, 2, 3)
            if note:
                d.text(out, note, (end + 8, y + 18), 0.32, PALE, 1, 2)

        gx, gy, gw = lx, self.gy, col_w - 44
        d.rect(out, (gx, gy), (gx + gw, gy + 6), DIM, -1)
        gap = info.get("gap")
        if found and gap is not None:
            d.rect(out, (gx, gy), (gx + gw * min(gap, 0.6) / 0.6, gy + 6), BLUE, -1)
            d.text(out, f"{gap:.2f}", (gx + gw + 8, gy + 8), 0.36, WHITE, 1, 1)
        for v, c, show in ((0.20, WHITE, True), (0.25, PALE, False), (0.40, GREY, True)):
            x = gx + gw * v / 0.6
            d.line(out, (x, gy - 3), (x, gy + 10), c, 1)
            if show:
                d.text(out, f"{v:.2f}"[1:], (x - 8, gy + 24), 0.3, c, 1, 1)

        # --- right column ---
        rx, ry = self.rx, self.ry
        d.text(out, f"{info.get('fps', 0):.0f}", (rx, ry + 34), 1.0, WHITE, 2, 2, FONT_BOLD, right=True)
        d.text(out, f"DETECT {info.get('detect_ms', 0):.0f} MS", (rx, ry + 54), 0.36, WHITE, 1, 2, right=True)
        d.text(out, f"LAG {info.get('lag_ms', 0):.0f} MS", (rx, ry + 72), 0.36, WHITE, 1, 2, right=True)
        view_word = "VIEW HAND" if not cam else f"VIEW CAM {int(round(self.strength * 100))}%"
        rows_sw = [("CURSOR", info.get("cursor_on", False)), ("DRAW", info.get("draw_on", False)), (view_word, True)]
        for i, (name, on) in enumerate(rows_sw):
            y = self.sy + i * 22
            d.circle(out, (rx - 4, y - 4), 4, BLUE if on else DIM, -1)
            word = name if name.startswith("VIEW") else f"{name} {'ON' if on else 'OFF'}"
            d.text(out, word, (rx - 16, y), 0.38, WHITE if on else GREY, 1, 3, right=True)
        return out

    def _bracket(self, img, c, state, progress):
        """Rounded corner brackets (from the reference picture) plus state details."""
        d = self.d
        cx, cy = c
        wide = state in ("PRESSED", "DRAG", "DRAWING", "SCROLLING")
        r, h, arm, rad = (36, 30, 14, 8) if not wide else (30, 26, 12, 8)
        color = BLUE if wide else WHITE
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = cx + sx * r, cy + sy * h
                d.line(img, (x, y - sy * rad), (x, y - sy * (rad + arm)), color, 2)
                d.line(img, (x - sx * rad, y), (x - sx * (rad + arm), y), color, 2)
                start = {(-1, -1): 180, (1, -1): 270, (1, 1): 0, (-1, 1): 90}[(sx, sy)]
                d.arc(img, (x - sx * rad, y - sy * rad), rad, start, start + 90, color, 2)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):          # small blue ticks
            a = (cx + dx * (r + 8 if dx else 0), cy + dy * (h + 8 if dy else 0))
            b = (cx + dx * (r + 16 if dx else 0), cy + dy * (h + 16 if dy else 0))
            d.line(img, a, b, BLUE, 2)
        if state == "PINCH" and progress > 0:                        # hold timer fills a ring
            d.arc(img, c, 18, -90, -90 + 360 * progress, BLUE, 3)
        if state in ("PRESSED", "DRAG"):
            d.circle(img, c, 14, BLUE, 3)
        if state == "DRAWING":
            d.circle(img, c, 8, BLUE, -1)
        if state.startswith("SCROLL"):
            d.arrow(img, (cx, cy - 6), (cx, cy - 22), BLUE, 2)
            d.arrow(img, (cx, cy + 6), (cx, cy + 22), BLUE, 2)
        if state == "RIGHT":
            d.circle(img, c, 20, BLUE, 1)
        d.rect(img, (cx - 3, cy - 3), (cx + 3, cy + 3), BLUE, -1)
