"""
panel_logic.py - the plain-Python parts of the music window (where things are, what a click means).
Kept apart from panel.py so it can be tested anywhere, without a Mac.

All numbers are "design units" with (0, 0) at the TOP-LEFT of the window. The real window can be
bigger or smaller: panel.py scales everything evenly, and divides mouse positions back into these units.
"""

W, H = 360, 252
CUT = 16                     # how much each corner of the frame is cut off
MIN_W, MAX_W = 260, 720      # how small / big the window can be made


def fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def ellipsize(text: str, fits) -> str:
    """Shorten text with '...' until fits(text) says it's narrow enough."""
    if fits(text):
        return text
    while len(text) > 1 and not fits(text + "..."):
        text = text[:-1]
    return text.rstrip() + "..."


def frame_points(inset: float = 0.0):
    """The cut-corner outline of the window (8 points)."""
    i, c = inset, CUT
    return [(c, i), (W - c, i), (W - i, c), (W - i, H - c), (W - c, H - i), (c, H - i), (i, H - c), (i, c)]


def clamp_width(w: float) -> float:
    return min(MAX_W, max(MIN_W, w))


class Layout:
    """Rectangles are (x, y, w, h)."""

    close = (W - 90, 10, 72, 30)
    art = (20, 56, 96, 96)
    text_x = 132
    title_y, artist_y, state_y = 58, 86, 114
    volume = (166, 138, 174, 8)        # the drawn bar
    progress = (20, 172, 320, 6)
    prev = (20, 198, 100, 32)
    play = (130, 198, 100, 32)
    next = (240, 198, 100, 32)
    grip = (318, 231, 26, 16)          # the little mark that is drawn
    # ...but you can start a resize from a much bigger area: the right edge, the bottom edge, the corner
    grip_zones = ((W - 16, 44, 16, H - 44), (0, H - 14, W, 14), (W - 56, H - 34, 56, 34))

    @staticmethod
    def grow(rect, dx=0, dy=0):
        x, y, w, h = rect
        return (x - dx, y - dy, w + 2 * dx, h + 2 * dy)

    @staticmethod
    def inside(rect, p) -> bool:
        x, y, w, h = rect
        return x <= p[0] <= x + w and y <= p[1] <= y + h

    @classmethod
    def hit(cls, p):
        """What did a click at point p press? Returns (name, value) or None (None = empty glass: drag to move).
        'seek' / 'volume' carry a 0..1 fraction along their bar. Bars get a taller click area
        because pointing with a finger is less exact than a mouse."""
        for name in ("close", "prev", "play", "next"):
            if cls.inside(getattr(cls, name), p):
                return name, None
        if any(cls.inside(z, p) for z in cls.grip_zones):
            return "grip", None
        if cls.inside(cls.grow(cls.progress, 0, 10), p):
            return "seek", cls.fraction(cls.progress, p)
        if cls.inside(cls.grow(cls.volume, 0, 10), p):
            return "volume", cls.fraction(cls.volume, p)
        return None

    @staticmethod
    def fraction(rect, p) -> float:
        x, _, w, _ = rect
        return min(1.0, max(0.0, (p[0] - x) / w))
