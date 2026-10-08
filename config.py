"""
config.py - FIVES's personality and settings.

This is the file you edit to make FIVES yours. Nothing in here "runs";
it's just values the other files read. Change a value, save, restart FIVES.
"""

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
NAME = "FIVES"
USER_NAME = "Hoyu"

# The system message (Lesson 1). This paragraph IS the personality.
PERSONALITY = (
    f"You are {NAME}, a personal assistant living on {USER_NAME}'s Mac. "
    "You are calm, sharp, and brief, like a good co-pilot. "
    "When a request can be done with one of your tools, call the tool. "
    "If nothing fits, just answer. Keep replies to one or two sentences."
)

# ---------------------------------------------------------------------------
# Brain (Lesson 1)
# ---------------------------------------------------------------------------
# Qwen 3.6 35B-A3B: a "mixture of experts" model. It knows as much as a 35B
# model but only uses 3B of its numbers per word, so it answers fast.
# About 23 GB, which fits comfortably in your 48 GB. Download it first:
#   ollama pull qwen3.6:35b
#
# Other options to try (change this one line, restart FIVES, compare):
#   "qwen3.6:35b-mlx"  same model, packaged for Apple's chip. Might be faster
#   "qwen3.6:27b"      denser and a bit smarter, but slower to answer
#   "qwen3.5:9b"       small and quick, if you want a lightweight fallback
MODEL = "qwen3.6:35b"

# "Thinking" lets the model reason silently before answering. Better for hard
# problems, but it adds seconds of delay. A command assistant wants speed.
#   False = off (fast)   True = on (slower, smarter)   None = model's default
THINK = False

# How many tokens (Lesson 1) the model can see at once. Bigger remembers more
# of the conversation but uses more memory. 16384 is plenty for FIVES.
CONTEXT_TOKENS = 16384

# 0 = pick the most likely action every time. Best for reliable tool use.
TEMPERATURE = 0

# How long Ollama keeps the model loaded in memory after your last request.
# Loading takes a while, so a long time here means FIVES answers fast all day.
KEEP_ALIVE = "2h"

# Safety valve: the most tool calls FIVES may make for one request.
MAX_TOOL_ROUNDS = 5

# ---------------------------------------------------------------------------
# Voice (Lesson 5) - uses the Mac's built-in `say` command
# ---------------------------------------------------------------------------
SPEAK_REPLIES = False       # True = FIVES reads replies out loud
VOICE = "Samantha"          # see all voices: say -v '?'
SPEECH_RATE = 190           # words per minute

# ---------------------------------------------------------------------------
# Eyes (Lesson 4)
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0            # 0 = built-in camera. Try 1 for an external one
MIRROR = True               # flip the image so it moves like a mirror

# Pinch = thumb tip close to index tip. Measured as a fraction of hand size,
# so it works whether your hand is near or far from the camera.
PINCH_START = 0.20          # closer than this -> pinch begins
PINCH_END = 0.25            # farther than this -> pinch ends
# Letting go FAST: the pinch also ends as soon as the gap grows this much beyond
# the tightest it got. This is what makes clicks feel immediate. Pinches ending
# by accident while you drag? raise it (0.14). Clicks still feel slow? lower it (0.07).
PINCH_RELEASE_MARGIN = 0.10
# ...but while you are DRAGGING, only a clearly open hand counts as letting go.
# Drags still dropping by accident? raise it (0.50). Drops feel slow? lower it (0.35).
PINCH_DRAG_END = 0.40

# Camera picture size and speed. A smaller picture is faster to analyze,
# which means a higher frame rate and a less laggy cursor.
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30

# Smoothing for the fingertip (the "One Euro filter", see gestures.py).
# MIN_CUTOFF: steadiness when your finger is still. Lower = steadier but floatier.
# BETA: how fast it stops smoothing when you move. Higher = less lag, more shake.
# Tuning tip: shaky while holding still? lower MIN_CUTOFF.
#             laggy when moving fast?     raise BETA.
MIN_CUTOFF = 1.5
BETA = 8.0

# When you pinch, the click lands where your fingertip was this many seconds
# BEFORE the pinch was detected, so the finger dip doesn't move your click.
# Too much dip still? raise it (0.3). Click lands behind your motion? lower it.
REWIND_SECONDS = 0.25

# Cursor control. Off by default. Press "c" in the camera window to toggle.
CONTROL_CURSOR = False
# Only the middle part of the camera image maps to your screen, so you can
# reach the screen edges without your finger leaving the camera's view.
CURSOR_MARGIN = 0.15

# ---------------------------------------------------------------------------
# Clicking, dragging, right click, scroll (cursor mode only)
# ---------------------------------------------------------------------------
# LEFT CLICK: pinch (thumb + index), then let go. The click happens on release,
# like a real mouse. Two quick clicks in a row = double-click, three = triple.
#
# DRAG: pinch, then MOVE your hand. The button goes down and the cursor follows
# you until you let go. Great for dragging Chrome tabs and windows.
#
# HOLD: pinch and keep still. After HOLD_TO_PRESS_SECONDS the button goes down
# anyway (for press-and-hold menus). The ring around your fingertip fills up so
# you can see it coming. Set it to 0 to turn this off.
HOLD_TO_PRESS_SECONDS = 0.4

# How far your HAND (knuckles, not fingertip) must move, as a fraction of the
# camera picture, before a pinch becomes a drag. Clicks turning into drags?
# raise it. Drag feels stiff to start? lower it.
DRAG_DISTANCE = 0.05

# Tracking sometimes flickers for a frame. During a drag, the pinch must stay
# open this long before we let go, so you don't drop things by accident.
RELEASE_GRACE_SECONDS = 0.15

# If your hand leaves the camera mid-drag, let go after this long.
LOST_HAND_RELEASE_SECONDS = 0.3

# Double-click: the second click must come within this many seconds, and
# (roughly) in the same place.
DOUBLE_CLICK_SECONDS = 0.6     # air pinches are slower than mouse clicks, so this is generous
DOUBLE_CLICK_DISTANCE = 0.03

# RIGHT CLICK: pinch with thumb + index, and ALSO bring your middle fingertip to
# the thumb and keep it there for RIGHT_CLICK_FRAMES frames (3 = about 0.1 s), so a
# middle finger drifting by during a normal pinch doesn't count.
# RIGHT_CLICK_GAP is the middle-finger-to-thumb gap, as a fraction of hand size.
# Left clicks turning into right clicks? lower the gap (0.15) or raise the frames.
# Right click hard to trigger? raise the gap (0.25) or lower the frames.
RIGHT_CLICK_GAP = 0.20
RIGHT_CLICK_FRAMES = 3

# SCROLL MODE: while you HOLD the hotkey below, your index pinch becomes a "finger on the
# screen": pinch, move your hand up/down and the page follows, let go and a flick keeps
# gliding. The cursor freezes in place and clicking is paused; let go of the keys and
# everything is back to normal. It works from any app.
# Hotkey: any of "cmd", "shift", "ctrl", "alt" (alt = Option). Modifier keys alone, no
# letter, so no app reacts to them. Needs  pip install pynput  and macOS Input Monitoring
# permission (System Settings > Privacy & Security > Input Monitoring > Terminal).
# Set to [] to turn scroll mode off completely.
SCROLL_HOTKEY = ["cmd", "shift"]
SCROLL_GAIN = 2500            # pixels scrolled when your hand crosses the whole picture height
SCROLL_DIRECTION = 1          # 1 = natural (like a trackpad). If it feels backwards, use -1
SCROLL_ENTER_FRAMES = 2       # the pinch must hold this many frames before scrolling starts
# Acceleration: faster swipes scroll farther (up to 4x). 0 = same distance at any speed.
SCROLL_ACCEL = 1.0
# Momentum: let go of the pinch while your hand is moving and the page keeps gliding,
# slowing to a stop over roughly this many seconds. Flick, lift, flick again.
# 0 turns the glide off. Glides too long? lower it (0.25). Stops too soon? raise it (0.6).
SCROLL_MOMENTUM_SECONDS = 0.4
