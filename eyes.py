"""
eyes.py - FIVES sees your hand.   Run:  python eyes.py

What happens each frame (about 30 times a second):
  1. grab the newest picture from the webcam
  2. hand it to MediaPipe, which finds 21 points on your hand
  3. turn those points into meaning: where's the fingertip? what gesture is it?
  4. draw it on screen, and (in cursor mode) drive the mouse

Keys in the camera window:  q = quit   c = cursor control on/off

Gestures in cursor mode:
  point (index finger)          move the cursor
  pinch (thumb + index), let go click    (quick, twice = double-click)
  pinch, then move your hand    drag     (hold still 0.4 s = press and hold)
  pinch with thumb + index + middle      right click
  SCROLL MODE (hold Cmd+Shift):
      pinch, move your hand up/down  scroll   (let go while moving: it glides)
  DRAW MODE (hold Cmd+Option):
      pinch = pen down at once, let go = pen up (no tail). For sketch pads.
"""

import threading
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp

import config
import gestures as g
import hotkey
import hud as hud_mod


class LatestFrame:
    """Reads the camera on its own thread and always keeps only the NEWEST picture.

    Why: the camera hands pictures over in a queue. If our loop is even slightly
    slower than the camera, old pictures pile up and we end up looking at where
    your hand was a few frames ago. That is pure lag. A thread that keeps
    reading and throws away old pictures fixes it. It also lets the camera grab
    the next picture while we are still analyzing the current one.
    """

    def __init__(self, camera):
        self.camera = camera
        self.cond = threading.Condition()
        self.frame = None
        self.stamp = 0.0        # when the picture was taken (seconds)
        self.seq = 0            # counts pictures, so we never use one twice
        self.done = False
        self.stopping = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.stopping:
            ok, frame = self.camera.read()
            stamp = time.monotonic()
            with self.cond:
                if not ok:
                    self.done = True
                    self.cond.notify_all()
                    return
                self.frame, self.stamp = frame, stamp
                self.seq += 1
                self.cond.notify_all()

    def read(self, last_seq: int):
        """Wait for a picture newer than last_seq. Returns (ok, frame, stamp, seq)."""
        with self.cond:
            while self.seq == last_seq and not self.done:
                self.cond.wait(timeout=1.0)
            if self.seq == last_seq:                  # camera ended, nothing new
                return False, None, 0.0, last_seq
            return True, self.frame, self.stamp, self.seq

    def close(self) -> None:
        self.stopping = True
        self.thread.join(timeout=1.0)


class Mouse:
    """Drives the Mac's mouse. Talks to macOS (Quartz) directly, because it's faster
    than pyautogui; falls back to pyautogui if Quartz isn't available.

    Emergency brake: if YOU push the mouse into a screen corner, brake_hit() is True
    and eyes.py stops. (Our own moves stay a few pixels away from corners.)
    """

    def __init__(self):
        import pyautogui
        pyautogui.PAUSE = 0
        self.pag = pyautogui
        self.screen_w, self.screen_h = pyautogui.size()
        try:
            import Quartz
            self.q = Quartz
        except ImportError:
            self.q = None
        self.strip_flags = False     # True in scroll/draw mode: hide the held hotkey from apps
        # With Quartz we check the corners ourselves; otherwise pyautogui does.
        pyautogui.FAILSAFE = self.q is None

    # -- small helpers --------------------------------------------------------
    def at_corner(self) -> bool:
        p = self.q.CGEventGetLocation(self.q.CGEventCreate(None))
        near = lambda v, size: v <= 2 or v >= size - 3
        return near(p.x, self.screen_w) and near(p.y, self.screen_h)

    def _post(self, kind, x, y, button=None, count=0) -> None:
        """Send one mouse event to macOS."""
        q = self.q
        button = q.kCGMouseButtonLeft if button is None else button
        event = q.CGEventCreateMouseEvent(None, kind, (x, y), button)
        if count:
            q.CGEventSetIntegerValueField(event, q.kCGMouseEventClickState, count)
        if self.strip_flags and hasattr(q, "CGEventSetFlags"):
            q.CGEventSetFlags(event, 0)      # apps see a plain mouse, not Cmd/Option held
        q.CGEventPost(q.kCGHIDEventTap, event)

    def _goto(self, x, y) -> None:
        self._post(self.q.kCGEventMouseMoved, x, y)

    # -- moving ---------------------------------------------------------------
    def brake_hit(self) -> bool:
        """True if YOU pushed the mouse into a screen corner (the emergency brake)."""
        return self.q is not None and self.at_corner()

    def move(self, x: int, y: int) -> None:
        """Move the cursor."""
        if self.q is None:
            self.pag.moveTo(x, y)
        else:
            self._goto(x, y)

    def drag(self, x: int, y: int) -> None:
        """Move the cursor WHILE the button is held. Apps need 'dragged' events for this."""
        if self.q is None:
            self.pag.dragTo(x, y, duration=0, button="left", mouseDownUp=False)
        else:
            self._post(self.q.kCGEventLeftMouseDragged, x, y)

    # -- buttons --------------------------------------------------------------
    def down(self, x: int, y: int) -> None:
        if self.q is None:
            self.pag.mouseDown(x, y)
            return
        self._goto(x, y)
        self._post(self.q.kCGEventLeftMouseDown, x, y, count=1)

    def up(self, x: int, y: int) -> None:
        if self.q is None:
            self.pag.mouseUp(x, y)
            return
        self._post(self.q.kCGEventLeftMouseUp, x, y, count=1)

    def click(self, x: int, y: int, count: int = 1) -> None:
        """One click. count says which click this is (2 = the second of a double-click)."""
        if self.q is None:
            self.pag.click(x, y)
            return
        self._goto(x, y)
        self._post(self.q.kCGEventLeftMouseDown, x, y, count=count)
        self._post(self.q.kCGEventLeftMouseUp, x, y, count=count)

    def right_click(self, x: int, y: int) -> None:
        if self.q is None:
            self.pag.rightClick(x, y)
            return
        q = self.q
        self._goto(x, y)
        self._post(q.kCGEventRightMouseDown, x, y, button=q.kCGMouseButtonRight, count=1)
        self._post(q.kCGEventRightMouseUp, x, y, button=q.kCGMouseButtonRight, count=1)

    def scroll(self, pixels: int) -> None:
        """Scroll by this many pixels (positive = the way a trackpad scrolls 'up')."""
        if self.q is None:
            self.pag.scroll(int(pixels / 20) or (1 if pixels > 0 else -1))
            return
        q = self.q
        event = q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitPixel, 1, int(pixels))
        # You may be holding Cmd+Shift for scroll mode. Don't let the apps see those keys
        # on the scroll (Cmd + scroll can zoom): send a plain, unmodified scroll.
        if hasattr(q, "CGEventSetFlags"):
            q.CGEventSetFlags(event, 0)
        q.CGEventPost(q.kCGHIDEventTap, event)


MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
MODEL_PATH = Path(__file__).parent / "models" / "hand_landmarker.task"

# Colors are (Blue, Green, Red) in OpenCV, not RGB.
# The palette is 501st Legion blue: one bright blue, a dim version, a pale one.
BLUE = (255, 150, 40)        # bright 501st blue
BLUE_DIM = (150, 90, 30)     # for thin, quiet lines
BLUE_PALE = (255, 215, 170)  # for small highlights
TEXT = (240, 240, 240)


# Which of the 21 points connect to which (pairs of landmark numbers).
HAND_BONES = [
    (0, 1), (1, 2), (2, 3), (3, 4),            # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),            # index
    (5, 9), (9, 10), (10, 11), (11, 12),       # middle
    (9, 13), (13, 14), (14, 15), (15, 16),     # ring
    (13, 17), (17, 18), (18, 19), (19, 20),    # pinky
    (0, 17),                                   # palm edge
]


def lock_window_shape(title: str, w: int, h: int) -> bool:
    """Mac only: keep the eyes window the same shape as the picture while you resize it.
    (Without this, a tall window leaves gray space on top and pushes the picture to the bottom.)
    Returns True once it worked, False if the window wasn't ready or this isn't a Mac."""
    try:
        from AppKit import NSApplication, NSMakeSize
        for win in NSApplication.sharedApplication().windows():
            if str(win.title()) == title:
                win.setContentAspectRatio_(NSMakeSize(w, h))
                return True
    except Exception:
        pass
    return False


def ensure_model() -> str:
    """Download the hand-tracking model the first time (a few megabytes)."""
    if not MODEL_PATH.exists():
        MODEL_PATH.parent.mkdir(exist_ok=True)
        print("Downloading the hand model (first run only)...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return str(MODEL_PATH)


def make_landmarker():
    """Load MediaPipe's hand landmarker in VIDEO mode (one frame at a time, in order)."""
    vision = mp.tasks.vision
    # Force the CPU. MediaPipe's default tries Apple's GPU path first, which
    # crashes on some Macs ("Service is unavailable"). On Apple chips the CPU
    # is plenty fast for one hand.
    delegate = mp.tasks.BaseOptions.Delegate.CPU
    options = vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=ensure_model(), delegate=delegate),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=1,
    )
    return vision.HandLandmarker.create_from_options(options)


def draw_hand(frame, points):
    """Draw the skeleton: thin pale-blue lines between joints, small dots on joints."""
    h, w = frame.shape[:2]
    px = [(int(x * w), int(y * h)) for x, y in points]
    for a, b in HAND_BONES:
        cv2.line(frame, px[a], px[b], BLUE_PALE, 1, cv2.LINE_AA)
    for p in px:
        cv2.circle(frame, p, 3, BLUE, -1, cv2.LINE_AA)


def draw_reticle(frame, center, state: str, progress: float) -> None:
    """The ring around your fingertip. Quiet when idle, alive when you act.

      idle     thin ring, four tick marks, a dot
      PINCH    ring brightens; a bright arc sweeps around as the hold timer fills
      PRESSED  button is down: the ring goes solid with a filled core
      DRAG     same, plus an outer ring so you can see you're carrying something
      RIGHT    a second ring appears (right click armed)
      SCROLL   up and down arrows (ring solid while your pinch is touching)
      DRAW     pen up: a small ring and dot.  DRAWING: pen down, solid dot and bright ring
    """
    cx, cy = center
    c = (cx, cy)
    R = 18
    if state in ("DRAW", "DRAWING"):
        if state == "DRAWING":                 # pen down: solid dot and a bright ring
            cv2.circle(frame, c, 11, BLUE, 2, cv2.LINE_AA)
            cv2.circle(frame, c, 5, BLUE, -1, cv2.LINE_AA)
        else:                                  # pen up: a small ring and a dot
            cv2.circle(frame, c, 10, BLUE, 1, cv2.LINE_AA)
            cv2.circle(frame, c, 2, BLUE_PALE, -1, cv2.LINE_AA)
        return
    if state in ("SCROLL", "SCROLLING"):
        cv2.circle(frame, c, R, BLUE if state == "SCROLLING" else BLUE_DIM,
                   2 if state == "SCROLLING" else 1, cv2.LINE_AA)
        cv2.arrowedLine(frame, (cx, cy - 5), (cx, cy - R - 12), BLUE, 2, cv2.LINE_AA, tipLength=0.45)
        cv2.arrowedLine(frame, (cx, cy + 5), (cx, cy + R + 12), BLUE, 2, cv2.LINE_AA, tipLength=0.45)
        return

    quiet = state in ("", "PINCH")           # quiet ring, so the filling arc stands out
    cv2.circle(frame, c, R, BLUE_DIM if quiet else BLUE, 1 if quiet else 2, cv2.LINE_AA)
    if state in ("", "PINCH", "RIGHT"):
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):             # four small tick marks
            cv2.line(frame, (cx + dx * (R + 4), cy + dy * (R + 4)),
                     (cx + dx * (R + 9), cy + dy * (R + 9)), BLUE_DIM, 1, cv2.LINE_AA)
    if state == "PINCH" and progress > 0:
        cv2.ellipse(frame, c, (R, R), 0, -90, -90 + 360 * progress, BLUE, 3, cv2.LINE_AA)
    if state == "RIGHT":
        cv2.circle(frame, c, R + 9, BLUE, 1, cv2.LINE_AA)
    if state in ("PRESSED", "DRAG"):
        cv2.circle(frame, c, R, BLUE, 3, cv2.LINE_AA)
        cv2.circle(frame, c, 6, BLUE, -1, cv2.LINE_AA)
        if state == "DRAG":
            cv2.circle(frame, c, R + 8, BLUE_DIM, 1, cv2.LINE_AA)
    else:
        cv2.circle(frame, c, 2, BLUE_PALE, -1, cv2.LINE_AA)


CLICK_NAMES = {1: "click", 2: "double-click", 3: "triple-click"}


def main() -> None:
    mouse = None             # created the first time you turn cursor control on

    camera = cv2.VideoCapture(config.CAMERA_INDEX)
    if not camera.isOpened():
        print("Couldn't open the camera. Check System Settings > Privacy & Security > Camera.")
        return
    # Ask for a small, fast picture. (The camera may pick the closest it supports.)
    cam_w, cam_h = ((config.HUD_CAMERA_WIDTH, config.HUD_CAMERA_HEIGHT) if config.HUD
                    else (config.CAMERA_WIDTH, config.CAMERA_HEIGHT))
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, cam_w)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_h)
    camera.set(cv2.CAP_PROP_FPS, config.CAMERA_FPS)

    frames = LatestFrame(camera)     # keeps only the newest picture (see class above)
    seq = 0
    landmarker = make_landmarker()
    pinch = g.PinchDetector(config.PINCH_START, config.PINCH_END, config.PINCH_RELEASE_MARGIN,
                            config.PINCH_DRAG_END)
    smooth = g.OneEuroFilter(config.MIN_CUTOFF, config.BETA)
    palm_smooth = g.OneEuroFilter(config.MIN_CUTOFF, config.BETA)   # same, for the knuckles
    history = g.PositionHistory()
    palm_history = g.PositionHistory()      # where the knuckles were (for the draw pen)
    engine = g.ClickEngine(config.DRAG_DISTANCE, config.HOLD_TO_PRESS_SECONDS,
                           config.RELEASE_GRACE_SECONDS, config.LOST_HAND_RELEASE_SECONDS,
                           config.DOUBLE_CLICK_SECONDS, config.DOUBLE_CLICK_DISTANCE,
                           config.RIGHT_CLICK_FRAMES)
    scroller = g.ScrollTracker(config.SCROLL_GAIN, config.SCROLL_DIRECTION,
                               config.SCROLL_ENTER_FRAMES, config.MIN_CUTOFF, config.BETA,
                               config.SCROLL_ACCEL, config.SCROLL_MOMENTUM_SECONDS)
    scroll_mode = False       # scroll mode is on right now (while you hold the hotkey)
    scroll_anchor = None     # where the cursor stays parked while scroll mode is on
    pen = g.DrawPen(config.DRAW_LIFT_GUARD, config.LOST_HAND_RELEASE_SECONDS)
    settle = g.ReleaseSettle(config.DRAG_SETTLE_SECONDS, config.DRAG_SETTLE_BLEND)
    draw_mode = False         # draw mode is on right now (while you hold its hotkey)
    frame_time = [0.0]        # the time of the picture being processed (perform() reads it)
    keypen = g.KeyPen(config.DRAW_GAIN, config.LOST_HAND_RELEASE_SECONDS, config.DRAW_RESYNC_SECONDS)
    draw_smooth = g.OneEuroFilter(config.DRAW_MIN_CUTOFF, config.DRAW_BETA)   # extra-calm fingertip for drawing
    key_draw = False          # key draw mode is on (toggled by tapping its hotkey)
    use_key_pen = config.DRAW_PEN == "key"
    watcher = draw_watcher = toggle = pen_key = None
    if config.SCROLL_HOTKEY:
        watcher = hotkey.HotkeyWatcher(config.SCROLL_HOTKEY)
        watcher.start()
    if use_key_pen:
        toggle = hotkey.HotkeyWatcher(config.DRAW_TOGGLE_HOTKEY)
        toggle.start()
        pen_key = hotkey.HotkeyWatcher([config.DRAW_PEN_KEY])
        pen_key.start()
    elif config.DRAW_HOTKEY:
        draw_watcher = hotkey.HotkeyWatcher(config.DRAW_HOTKEY)
        draw_watcher.start()
    hud = (hud_mod.Hud(config.HUD_WIDTH, config.HUD_HEIGHT, config.HUD_VIEW, config.HUD_GLOW,
                       config.HUD_SCALE, config.HUD_STRENGTH, config.HUD_DENOISE) if config.HUD else None)
    window = f"{config.NAME} eyes"
    if hud is not None:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window, *hud.size)       # shown at layout size; drawn at HUD_SCALE x for sharpness
    shape_locked = hud is None        # tries a few frames after the window opens, then stops
    shape_tries = 0
    last_gap = [0.0]      # newest thumb-index gap, only used to explain why a button let go
    last_sent = None      # the last cursor spot we sent, so we only send when it changes
    cursor_on = config.CONTROL_CURSOR
    last = time.monotonic()
    fps = 0.0
    detect_ms = 0.0      # how long hand-finding takes (smoothed)
    pipe_ms = 0.0        # picture taken -> hand found (smoothed). This is OUR share of the lag.

    def to_px(pos):
        """Camera position (0..1) -> screen pixels."""
        return g.to_screen(pos[0], pos[1], mouse.screen_w, mouse.screen_h, config.CURSOR_MARGIN)

    def perform(actions) -> None:
        """Carry out what the click engine decided."""
        for act in actions:
            kind = act[0]
            x, y = to_px(act[1])
            if kind == "click":
                mouse.click(x, y, act[2])
                print(CLICK_NAMES[act[2]])
            elif kind == "right_click":
                mouse.right_click(x, y)
                print("right-click")
            elif kind == "down":
                mouse.down(x, y)
                print("button down")
            elif kind == "up":
                mouse.up(x, y)
                print(f"button up   (thumb-index gap {last_gap[0]:.2f})")
                settle.start(frame_time[0], act[1])     # don't snap the cursor to the fingertip

    def set_swallow() -> None:
        """While key draw mode is on, hide the pen key from other apps; otherwise let it through."""
        if use_key_pen and config.DRAW_SWALLOW_PEN_KEY and hasattr(hotkey.HotkeyWatcher, "set_swallow"):
            hotkey.HotkeyWatcher.set_swallow([config.DRAW_PEN_KEY] if key_draw else [])

    def release_everything() -> None:
        """Let go of the button and stop any scroll. Safe to call any time."""
        nonlocal scroll_mode, scroll_anchor, draw_mode, key_draw
        if mouse is not None:
            perform(engine.reset())
            perform(pen.reset())
            perform(keypen.resync())
            mouse.strip_flags = False
        scroller.cancel()
        settle.cancel()
        scroll_mode = draw_mode = key_draw = False
        set_swallow()
        scroll_anchor = None

    print(f"{config.NAME} eyes online. q = quit, c = toggle cursor control, h = switch view, [ ] = blue tint.")
    print(f"Camera is giving {int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))} x {int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))}.")
    try:
        while True:
            ok, frame, stamp, seq = frames.read(seq)    # 1. newest picture (and when it was taken)
            if not ok:
                break
            if config.MIRROR:
                frame = cv2.flip(frame, 1)

            # With the HUD the picture is big. Hand tracking gets a small 4:3 copy from the middle
            # (the shape it always saw), and crop = (where that copy starts, how wide it is), 0..1.
            shown_frame, crop = frame, (0.0, 1.0)
            if hud is not None:
                fh_, fw_ = frame.shape[:2]
                if fw_ * 3 > fh_ * 4 + 8:                           # wider than 4:3: cut the sides
                    cw_ = int(fh_ * 4 / 3)
                    x0_ = (fw_ - cw_) // 2
                    crop = (x0_ / fw_, cw_ / fw_)
                    frame = frame[:, x0_:x0_ + cw_]
                if frame.shape[1] > config.TRACK_WIDTH:
                    frame = cv2.resize(frame, (config.TRACK_WIDTH, config.TRACK_WIDTH * 3 // 4),
                                       interpolation=cv2.INTER_AREA)

            # 2. MediaPipe wants RGB; OpenCV gives BGR. Timestamps must only go up.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            started = time.monotonic()
            result = landmarker.detect_for_video(image, int(stamp * 1000))
            found = time.monotonic()
            detect_ms = 0.9 * detect_ms + 0.1 * (found - started) * 1000
            pipe_ms = 0.9 * pipe_ms + 0.1 * (found - stamp) * 1000

            frame_time[0] = stamp
            hud_points = hud_aim = hud_gap = None     # what the HUD shows this frame
            hud_state, hud_progress = "", 0.0
            if toggle is not None and toggle.consume_tap() and cursor_on:
                if mouse is None:
                    mouse = Mouse()
                key_draw = not key_draw
                set_swallow()
                if key_draw:
                    keypen.resync()
                    print(f"draw mode ON  (hold {config.DRAW_PEN_KEY} to draw, tap {'+'.join(config.DRAW_TOGGLE_HOTKEY)} to leave)")
                else:
                    print("draw mode OFF")
                    perform(keypen.resync())
                    pinch.pinched = False       # a pinch held across the switch isn't a click
                    pinch.armed = False
            status = "no hand"
            if result.hand_landmarks:
                hand = result.hand_landmarks[0]         # first hand found
                points = [(lm.x, lm.y) for lm in hand]  # 21 (x, y) pairs, 0..1
                h, w = frame.shape[:2]

                # 3. meaning
                t = stamp                               # when the picture was TAKEN
                tip = smooth.update(*points[g.INDEX_TIP], t)
                history.add(t, *tip)
                # Your fingertip dips when you pinch, but your knuckles don't. So we
                # judge "did the HAND move?" (for dragging) by the knuckles.
                knuckles = ((points[g.INDEX_KNUCKLE][0] + points[g.MIDDLE_KNUCKLE][0]) / 2,
                            (points[g.INDEX_KNUCKLE][1] + points[g.MIDDLE_KNUCKLE][1]) / 2)
                palm = palm_smooth.update(*knuckles, t)
                palm_history.add(t, *palm)
                ratio = g.pinch_ratio(points)           # thumb <-> index gap
                last_gap[0] = ratio
                draw_tip = draw_smooth.update(*points[g.INDEX_TIP], t)    # calmer fingertip for key drawing
                mid_ratio = g.middle_ratio(points)      # thumb <-> middle gap
                # Dragging, or scrolling with your pinch held, gets a forgiving grip.
                # While drawing, the pen holds on until the pinch is clearly open (DRAW_HOLD_END);
                # the tail is cut by the pen stopping early (DrawPen), not by lifting early.
                pinch.hold_end = config.DRAW_HOLD_END if draw_mode else config.PINCH_DRAG_END
                pinch.update(ratio, holding=(engine.state == "down" or pen.down
                                             or (scroll_mode and scroller.active)))
                # Where were you pointing just BEFORE your finger dipped to pinch?
                rewound = history.seconds_ago(config.REWIND_SECONDS, t) or tip
                palm_rewound = palm_history.seconds_ago(config.REWIND_SECONDS, t) or palm

                aim = tip                               # where the ring (and cursor) goes
                state = ""                              # what to show: PINCH, DRAG, SCROLL...
                progress = 0.0
                if cursor_on:
                    if mouse is None:
                        mouse = Mouse()                 # only loaded if you use it

                    # Scroll mode is ON while its hotkey is held; draw mode while ITS hotkey is held.
                    # (If you hold both, scroll wins.)
                    wanted = watcher is not None and watcher.down
                    draw_wanted = draw_watcher is not None and draw_watcher.down and not wanted
                    if (draw_wanted and not draw_mode and not scroll_mode
                            and engine.state == "idle" and not pinch.pinched):
                        draw_mode = True                        # (never starts in the middle of a click)
                    elif draw_mode and not draw_wanted:
                        draw_mode = False
                        perform(pen.reset())                    # lift the pen
                        if pinch.pinched:                       # still pinching: don't turn that into a click
                            pinch.pinched = False
                            pinch.armed = False
                    if key_draw and wanted:
                        perform(keypen.reset())                 # scroll wins: lift the pen
                        keypen.hand_gone()
                    mouse.strip_flags = scroll_mode or draw_mode or key_draw
                    if wanted and not scroll_mode and not draw_mode and engine.state == "idle" and (key_draw or not pinch.pinched):
                        scroll_mode = True                      # (never starts in the middle of a click)
                        scroll_anchor = rewound                 # the cursor parks here
                    elif scroll_mode and not wanted:
                        scroll_mode = False
                        scroll_anchor = None
                        mouse.strip_flags = draw_mode or key_draw
                        if pinch.pinched:                       # still pinching: don't turn that into a click
                            pinch.pinched = False
                            pinch.armed = False

                    # In scroll mode your pinch is the "finger on the screen". We follow your
                    # KNUCKLES, not your fingertips, so curling a finger doesn't move the page.
                    touching = scroll_mode and pinch.pinched
                    if not scroll_mode and pinch.pinched:
                        scroller.cancel()                       # a click-pinch stops a glide, like touching a trackpad
                    pixels = scroller.update(t, touching, palm[1])     # also carries any glide
                    if pixels:
                        mouse.scroll(pixels)

                    if scroll_mode:
                        aim, state = scroll_anchor, "SCROLLING" if touching else "SCROLL"
                    elif key_draw:
                        # Key drawing: your hand only points; holding the pen key puts ink down.
                        perform(keypen.update(t, pen_key.down and not wanted, draw_tip))
                        aim = keypen.aim() or draw_tip
                        state = "DRAWING" if keypen.down else "DRAW"
                    elif draw_mode:
                        # Drawing: the pen goes down the instant you pinch and follows your knuckles.
                        pen_tip = history.seconds_ago(config.DRAW_REWIND_SECONDS, t) or tip
                        draw_palm = palm_history.seconds_ago(config.DRAW_REWIND_SECONDS, t) or palm
                        perform(pen.update(t, pinch.pinched, ratio, palm, pen_tip, draw_palm))
                        aim = pen.aim() or tip
                        state = "DRAWING" if pen.down else "DRAW"
                    else:
                        # Clicking and dragging (the engine decides what a pinch means).
                        perform(engine.update(t, pinch.pinched, palm, rewound,
                                              pinch.pinched and mid_ratio < config.RIGHT_CLICK_GAP,
                                              palm_rewound))
                        aim = engine.aim(palm) or tip
                        state = engine.label
                        progress = engine.hold_progress(t)

                    # Just let go of a drag or the pen? Ease the cursor over to your fingertip.
                    if not scroll_mode and engine.state == "idle" and not pen.down and not key_draw:
                        if settle.active and not settle.reported:
                            settle.reported = True
                            print(f"released: your fingertip is {g.distance(settle.pos, aim) * mouse.screen_w:.0f} px from the drop point")
                        aim = settle.apply(t, aim)
                    else:
                        settle.cancel()

                    if mouse.brake_hit():
                        print("Emergency brake: the mouse hit a screen corner. Stopping.")
                        break
                    sx, sy = to_px(aim)
                    if (sx, sy) != last_sent:           # a real mouse is silent when it's still
                        if engine.state == "down" or pen.down or keypen.down:
                            mouse.drag(sx, sy)
                        else:
                            mouse.move(sx, sy)
                        last_sent = (sx, sy)
                else:
                    state = "PINCH" if pinch.pinched else ""

                # 4. draw
                if hud is not None:
                    hud_points = [(crop[0] + x * crop[1], y) for x, y in points]    # tracked area -> whole picture
                    hud_aim = (crop[0] + aim[0] * crop[1], aim[1])
                    hud_gap = ratio
                    hud_state, hud_progress = state, progress
                else:
                    draw_hand(frame, points)
                    draw_reticle(frame, (int(aim[0] * w), int(aim[1] * h)), state, progress)
                status = (state or "tracking") + f"   idx {ratio:.2f}  mid {mid_ratio:.2f}"
            else:
                smooth.reset()
                palm_smooth.reset()
                draw_smooth.reset()
                history.clear()
                palm_history.clear()
                pixels = scroller.update(stamp, False, 0.0)    # a glide keeps going without the hand
                if pixels and cursor_on and mouse is not None:
                    mouse.scroll(pixels)
                if scroll_mode and not (watcher is not None and watcher.down):
                    scroll_mode = False                         # you let go of the keys while the hand was gone
                    scroll_anchor = None
                last_sent = None
                if cursor_on and mouse is not None:
                    perform(engine.lost(stamp))         # lets go if the hand stays gone
                    perform(pen.lost(stamp))
                    perform(keypen.lost(stamp))
                if draw_mode and not (draw_watcher is not None and draw_watcher.down):
                    draw_mode = False
                    perform(pen.reset())
                    if mouse is not None:
                        mouse.strip_flags = scroll_mode
                if engine.state == "idle":
                    pinch.pinched = False

            now = time.monotonic()
            fps = 0.9 * fps + 0.1 * (1 / max(now - last, 1e-6))
            last = now
            if hud is not None:
                # detect = time MediaPipe spends finding your hand.
                # lag    = time from the camera taking the picture to us knowing where the hand is.
                info = dict(fps=fps, detect_ms=detect_ms, lag_ms=pipe_ms, cursor_on=cursor_on,
                            draw_on=key_draw or draw_mode, gap=hud_gap)
                shown = hud.render(shown_frame, hud_points, hud_aim, hud_state, hud_progress, info)
            else:
                label = f"{status}   cursor {'ON' if cursor_on else 'off'}   {fps:.0f} fps"
                cv2.putText(frame, label, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEXT, 2)
                timing = f"detect {detect_ms:.0f} ms   lag {pipe_ms:.0f} ms"
                cv2.putText(frame, timing, (16, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEXT, 2)
                shown = frame
            cv2.imshow(window, shown)
            if not shape_locked and shape_tries < 60:
                shape_tries += 1
                shape_locked = lock_window_shape(window, *hud.size)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord("h") and hud is not None:
                print("view:", "camera" if hud.toggle() == "cam" else "hand only")
            if key == ord("t") and hud is not None:
                print(f"hologram: {'ON' if hud.toggle_holo() > 0 else 'OFF'}")
            if key in (ord("["), ord("]")) and hud is not None:
                print(f"blue tint: {hud.nudge(0.1 if key == ord(']') else -0.1):.0%}")
            if key == ord("c"):
                cursor_on = not cursor_on
                last_sent = None
                if not cursor_on:
                    release_everything()
    finally:
        release_everything()        # never leave the mouse button stuck down
        if watcher is not None:
            watcher.stop()
        for w in (draw_watcher, toggle, pen_key):
            if w is not None:
                w.stop()
        frames.close()
        camera.release()
        cv2.destroyAllWindows()
        landmarker.close()
    print(f"Average: detect {detect_ms:.0f} ms, lag {pipe_ms:.0f} ms, {fps:.0f} fps.")


if __name__ == "__main__":
    main()
