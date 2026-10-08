"""
gestures.py - the math that turns 21 hand points into meaning.

No camera here, just geometry, so you can test and tweak it on its own.
Every point is (x, y) where x and y go from 0.0 to 1.0 across the image:
(0, 0) is the top-left corner and (1, 1) is the bottom-right.
"""

import math

# The 21 landmarks MediaPipe finds on a hand, by index number.
WRIST = 0
THUMB_TIP = 4
INDEX_KNUCKLE = 5
INDEX_PIP = 6          # the middle joint of each finger
INDEX_TIP = 8
MIDDLE_KNUCKLE = 9
MIDDLE_PIP = 10
MIDDLE_TIP = 12
RING_PIP = 14
RING_TIP = 16
PINKY_PIP = 18
PINKY_TIP = 20


def distance(a, b) -> float:
    """Straight-line distance between two points (Pythagoras)."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def hand_size(points) -> float:
    """Wrist to middle knuckle. A ruler that grows and shrinks with the hand."""
    return distance(points[WRIST], points[MIDDLE_KNUCKLE]) or 1e-6


def pinch_ratio(points) -> float:
    """Thumb-to-index gap divided by hand size. Small number = pinching."""
    return distance(points[THUMB_TIP], points[INDEX_TIP]) / hand_size(points)


def middle_ratio(points) -> float:
    """Thumb-to-MIDDLE-finger gap divided by hand size. Used for right click."""
    return distance(points[THUMB_TIP], points[MIDDLE_TIP]) / hand_size(points)


def finger_extended(points, tip: int, pip: int, factor: float = 1.1) -> bool:
    """Is this finger sticking out? True when its tip is farther from the wrist
    than its middle joint is. A curled finger folds its tip back toward the palm."""
    return distance(points[WRIST], points[tip]) > distance(points[WRIST], points[pip]) * factor


def scroll_pose(points, factor: float = 1.1) -> bool:
    """Index and middle fingers up, ring and pinky curled."""
    return (finger_extended(points, INDEX_TIP, INDEX_PIP, factor)
            and finger_extended(points, MIDDLE_TIP, MIDDLE_PIP, factor)
            and not finger_extended(points, RING_TIP, RING_PIP, factor)
            and not finger_extended(points, PINKY_TIP, PINKY_PIP, factor))


class PinchDetector:
    """Decides pinched / not pinched, without flickering.

    START: the thumb-index gap must drop below `start` to begin a pinch.
    END:   normally the gap must rise above `end` to finish it (hysteresis, so
           tiny jitters near the line don't flip it on and off).

    release_margin makes letting go FAST: the pinch also ends as soon as the
    gap rises `release_margin` above the tightest it got during this pinch. A
    firm pinch (gap 0.10) then ends at 0.20 instead of waiting for 0.30, which
    is what makes clicks feel immediate. After a release a new pinch needs the
    fingers to open past `start` first, so you can't re-trigger by accident.
    """

    def __init__(self, start: float, end: float, release_margin: float = 0.0,
                 hold_end: float = 0.0):
        self.start = start
        self.end = end
        self.release_margin = release_margin
        self.hold_end = hold_end      # looser "let go" gap used while you are dragging
        self.pinched = False
        self.low = 1.0            # tightest gap seen during this pinch
        self.armed = True         # fingers have opened since the last pinch

    def update(self, ratio: float, holding: bool = False) -> str | None:
        """Feed the latest ratio. Returns "down", "up", or None (no change).

        holding=True means the button is down (you're dragging). The grip is then
        much more forgiving: moving your hand makes the gap wobble, and that must
        not be mistaken for letting go."""
        if not self.pinched:
            if ratio > self.start:
                self.armed = True
            if self.armed and ratio < self.start:
                self.pinched = True
                self.low = ratio
                return "down"
            return None
        self.low = min(self.low, ratio)
        limit = self.end
        if holding:
            limit = max(limit, self.hold_end)
        elif self.release_margin:
            limit = min(limit, self.low + self.release_margin)
        if ratio > limit:
            self.pinched = False
            self.armed = ratio > self.start
            return "up"
        return None


class Smoother:
    """Exponential moving average: each new position only moves us part way.

    amount=1.0 follows the raw point exactly (jittery).
    amount=0.2 moves 20% of the way each frame (smooth, slightly laggy).
    """

    def __init__(self, amount: float):
        self.amount = amount
        self.x = None
        self.y = None

    def update(self, x: float, y: float):
        if self.x is None:
            self.x, self.y = x, y
        else:
            self.x += (x - self.x) * self.amount
            self.y += (y - self.y) * self.amount
        return self.x, self.y

    def reset(self):
        self.x = self.y = None


class OneEuroFilter:
    """Smart smoothing: heavy when you're nearly still, light when you move fast.

    The simple Smoother above has one fixed setting, so you must choose between
    "steady but laggy" and "snappy but shaky". This filter picks automatically
    every frame based on how fast the point is moving:
      - slow or still  -> smooth a lot   (kills the shake)
      - fast           -> smooth a little (kills the lag)

    min_cutoff: how smooth it is when still. Lower = steadier. (try 0.5 to 3)
    beta:       how quickly it loosens up when you move. Higher = less lag. (try 2 to 20)
    """

    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        """Turn a 'cutoff' into how far to move this frame (0..1)."""
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def update(self, x: float, y: float, t: float):
        """x, y = raw point. t = time in seconds. Returns the smoothed point."""
        if self.x is None:
            self.x, self.y, self.t = x, y, t
            return x, y
        dt = max(t - self.t, 1e-3)
        self.t = t

        # How fast is the point moving? (itself smoothed a little)
        a_d = self._alpha(self.d_cutoff, dt)
        self.dx += a_d * ((x - self.x) / dt - self.dx)
        self.dy += a_d * ((y - self.y) / dt - self.dy)
        speed = math.hypot(self.dx, self.dy)

        # Faster movement -> higher cutoff -> follow the raw point more closely.
        a = self._alpha(self.min_cutoff + self.beta * speed, dt)
        self.x += a * (x - self.x)
        self.y += a * (y - self.y)
        return self.x, self.y

    def reset(self):
        self.x = self.y = self.t = None
        self.dx = self.dy = 0.0


class PositionHistory:
    """Remembers where the fingertip was over the last second.

    Why: when you pinch, your index finger dips just before the pinch is
    detected. Looking back a fraction of a second finds where you were
    actually pointing, before the dip.
    """

    def __init__(self, keep_seconds: float = 1.0):
        self.keep = keep_seconds
        self.items = []          # list of (time, x, y), oldest first

    def add(self, t: float, x: float, y: float) -> None:
        self.items.append((t, x, y))
        while self.items and t - self.items[0][0] > self.keep:
            self.items.pop(0)

    def seconds_ago(self, seconds: float, now: float):
        """Position from `seconds` ago (or the oldest we have). None if empty."""
        if not self.items:
            return None
        target = now - seconds
        found = self.items[0]
        for item in self.items:
            if item[0] <= target:
                found = item
            else:
                break
        return found[1], found[2]

    def clear(self) -> None:
        self.items = []


def to_screen(x: float, y: float, screen_w: int, screen_h: int, margin: float, pad: int = 6):
    """Map a camera point (0-1) to screen pixels, using only the middle of the image.

    With margin 0.15, the box from 0.15 to 0.85 covers the whole screen, so
    you can reach the corners without your finger leaving the camera.

    pad keeps the cursor a few pixels away from the very edge. pyautogui's
    emergency brake fires when the cursor touches a corner, so without this
    margin, reaching a corner would stop the whole program.
    """
    span = 1 - 2 * margin
    sx = min(max((x - margin) / span, 0.0), 1.0)
    sy = min(max((y - margin) / span, 0.0), 1.0)
    return (pad + int(sx * (screen_w - 1 - 2 * pad)),
            pad + int(sy * (screen_h - 1 - 2 * pad)))


class ClickEngine:
    """Turns pinches into mouse actions, the way a real mouse behaves.

    When a pinch starts NOTHING is sent yet. The engine waits to see what you do:
      - let go quickly            -> a click (fires on release, like a mouse)
      - let go with the middle finger also on the thumb -> a right click
      - move your hand            -> the button goes down and you are dragging
      - keep still for a while    -> the button goes down anyway (press and hold)
    Quick repeated clicks in the same place become double and triple clicks.

    Each frame you call update() and it returns a list of actions to perform:
      ("click", pos, count)   ("right_click", pos)   ("down", pos)   ("up", pos)
    pos is a camera position (0..1). aim() says where the cursor should be.
    Pure logic: no mouse, no camera, no clock of its own, so it's easy to test.
    """

    def __init__(self, drag_distance, hold_seconds, release_grace, lost_release,
                 double_click_seconds, double_click_distance, right_frames=1):
        self.right_frames = right_frames   # frames the middle finger must stay on the thumb
        self.right_count = 0
        self.drag_distance = drag_distance
        self.hold_seconds = hold_seconds
        self.release_grace = release_grace
        self.lost_release = lost_release
        self.double_click_seconds = double_click_seconds
        self.double_click_distance = double_click_distance
        self.state = "idle"          # "idle", "pending" (pinching, undecided), "down" (button held)
        self.right = False           # the middle finger joined this pinch
        self.moved = False           # we are dragging (moved past the dead zone)
        self.press_pos = None        # where the pinch landed (already corrected for the finger dip)
        self.start_tip = None        # where the hand (knuckles) was when the pinch began
        self.start_t = 0.0
        self.cursor = None           # last cursor position we asked for
        self.open_since = None       # when the pinch opened during a drag (flicker guard)
        self.lost_since = None       # when the hand disappeared
        self.last_click = None       # (time, position, count) of the previous click

    # -- what the window should show ----------------------------------------
    @property
    def label(self) -> str:
        if self.state == "pending":
            return "RIGHT" if self.right else "PINCH"
        if self.state == "down":
            return "DRAG" if self.moved else "PRESSED"
        return ""

    def hold_progress(self, t: float) -> float:
        """0..1: how close the hold-to-press timer is to firing (for the ring)."""
        if self.state == "pending" and not self.right and self.hold_seconds:
            return max(0.0, min(1.0, (t - self.start_t) / self.hold_seconds))
        return 0.0

    def aim(self, tip):
        """Where the cursor should be right now, or None to just follow the fingertip."""
        if self.state == "idle":
            return None
        if self.state == "down" and self.open_since is not None:
            return self.cursor                         # pinch is opening: hold still
        if self.state == "down" and self.moved:
            self.cursor = (self.press_pos[0] + tip[0] - self.start_tip[0],
                           self.press_pos[1] + tip[1] - self.start_tip[1])
        else:
            self.cursor = self.press_pos
        return self.cursor

    # -- the per-frame brain --------------------------------------------------
    def update(self, t, pinched, tip, rewound, right_intent):
        """t = time (s). pinched = thumb+index pinch. tip = a STEADY point on the
        hand (we pass the knuckles: the fingertip dips when you pinch, knuckles
        don't), used to tell if you moved. rewound = where the fingertip was just
        before the dip. right_intent = middle finger is on the thumb too.
        Returns a list of actions."""
        self.lost_since = None
        actions = []

        if self.state == "idle" and pinched:
            self.state = "pending"
            self.start_t, self.start_tip = t, tip
            self.press_pos = rewound or tip
            self.right = self.moved = False
            self.right_count = 0
            self.open_since = None

        if self.state == "pending":
            # The middle finger must STAY on the thumb for a few frames. One
            # frame of drift during a normal pinch must not make a right click.
            self.right_count = self.right_count + 1 if (pinched and right_intent) else 0
            if self.right_count >= self.right_frames:
                self.right = True
            if not pinched:                            # let go: it was a click
                if self.right:
                    actions.append(("right_click", self.press_pos))
                else:
                    actions.append(self._click(t))
                self.state = "idle"
            elif not self.right:
                if distance(tip, self.start_tip) > self.drag_distance:
                    self.moved = True
                    self._press(actions)
                elif self.hold_seconds and t - self.start_t >= self.hold_seconds:
                    self._press(actions)

        elif self.state == "down":
            if pinched:
                self.open_since = None
                if not self.moved and distance(tip, self.start_tip) > self.drag_distance:
                    self.moved = True
            else:
                if self.open_since is None:
                    self.open_since = t
                if t - self.open_since >= self.release_grace:
                    actions.append(("up", self.cursor or self.press_pos))
                    self.state = "idle"
                    self.open_since = None
        return actions

    def lost(self, t):
        """Call each frame the hand is NOT visible. Lets go if it's gone too long."""
        actions = []
        if self.state == "idle":
            return actions
        if self.lost_since is None:
            self.lost_since = t
        if t - self.lost_since >= self.lost_release:
            if self.state == "down":
                actions.append(("up", self.cursor or self.press_pos))
            self.state = "idle"
            self.open_since = None
        return actions

    def reset(self):
        """Let go of everything (cursor mode turned off, or quitting)."""
        actions = []
        if self.state == "down":
            actions.append(("up", self.cursor or self.press_pos))
        self.state = "idle"
        self.open_since = None
        return actions

    # -- helpers --------------------------------------------------------------
    def _press(self, actions) -> None:
        self.state = "down"
        self.open_since = None
        self.cursor = self.press_pos
        actions.append(("down", self.press_pos))

    def _click(self, t):
        pos, count = self.press_pos, 1
        last = self.last_click
        if (last and last[2] < 3 and t - last[0] <= self.double_click_seconds
                and distance(pos, last[1]) <= self.double_click_distance):
            count = last[2] + 1
            pos = last[1]            # same spot as before, or the Mac won't see a double-click
        self.last_click = (t, pos, count)
        return ("click", pos, count)


class ScrollTracker:
    """Two-finger scrolling like a trackpad: move your hand, the page moves.

    - Waits for the scroll pose to hold a couple of frames (so a flicker
      doesn't scroll), then turns how far your hand moved up/down into pixels.
    - ACCELERATION: a fast swipe scrolls farther than a slow one (factor
      1 + accel * speed, capped at 4x), like a real trackpad. Slow moves stay
      precise; one quick flick covers a long page.
    - MOMENTUM: if you drop the pose while your hand is still moving, the page
      keeps gliding and slows to a stop (an exponential fade over about
      `momentum_seconds`). Putting the pose back down, or pinching, stops it,
      like touching a trackpad. This is what lets you flick, lift, and flick again.
    Small leftover fractions are carried to the next frame so slow moves still scroll.
    """

    MIN_GLIDE = 40.0     # pixels/second: below this the glide stops

    def __init__(self, gain, direction, enter_frames, min_cutoff, beta,
                 accel=0.0, momentum_seconds=0.0):
        self.gain = gain
        self.direction = direction
        self.enter_frames = enter_frames
        self.accel = accel
        self.momentum_seconds = momentum_seconds
        self.filter = OneEuroFilter(min_cutoff, beta)
        self.last_t = None
        self.cancel()

    @property
    def active(self) -> bool:
        return self.frames >= self.enter_frames

    def update(self, t: float, pose: bool, y: float) -> int:
        """Call EVERY frame. pose = is the scroll pose held. y = hand height
        (0 top .. 1 bottom). Returns whole pixels to scroll this frame
        (positive = hand moved down), including any gliding."""
        dt = max(t - self.last_t, 1e-3) if self.last_t is not None else 1 / 30
        self.last_t = t

        if pose:
            self.gliding = False                    # touching it again stops the glide
            self.frames += 1
            smooth_y = self.filter.update(0.5, y, t)[1]
            pixels = 0
            if self.active and self.prev is not None:
                delta = smooth_y - self.prev
                factor = min(1 + self.accel * abs(delta) / dt, 4.0)
                moved = delta * self.gain * self.direction * factor
                raw = moved + self.remainder
                pixels = int(raw)
                self.remainder = raw - pixels
                self.velocity += (moved / dt - self.velocity) * 0.5    # smoothed pixels/second
            self.prev = smooth_y
            return pixels

        # Pose is off. If we just let go while moving, start gliding.
        if (self.active and self.momentum_seconds and not self.gliding
                and abs(self.velocity) > self.MIN_GLIDE):
            self.gliding = True
        self.frames = 0
        self.prev = None
        self.filter.reset()
        if self.gliding:
            raw = self.velocity * dt + self.remainder
            pixels = int(raw)
            self.remainder = raw - pixels
            self.velocity *= math.exp(-dt / self.momentum_seconds)
            if abs(self.velocity) < self.MIN_GLIDE:
                self.gliding = False
                self.velocity = 0.0
                self.remainder = 0.0
            return pixels
        self.velocity = 0.0
        self.remainder = 0.0
        return 0

    def cancel(self) -> None:
        """Stop everything, including any glide."""
        self.frames = 0
        self.prev = None
        self.remainder = 0.0
        self.velocity = 0.0
        self.gliding = False
        self.filter.reset()

    reset = cancel
