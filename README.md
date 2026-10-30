# FIVES

<!-- 📍 GIF 1 (main demo, 10-15 s): point, pinch-click, drag, scroll. Drag the file in here. -->

A personal assistant for iMac, an attempt to make a futuristic workflow that replaces keyboard and mouse with your hands. This project has two parts:

- **Eyes** (`eyes.py`): the webcam watches my hand and turns it into a mouse. Point to move, pinch to click, drag, scroll.
- **Brain** (`main.py`): a chat front end for a local language model (run through Ollama) that can use tools on the Mac.

Work in progress :D

## The idea

It has always been a pain for me to have a billion tabs open on chrome, and  

## Built vs planned

**Built**
- Hand-tracked mouse: move, click, double and triple click, drag, press-and-hold, right click, scroll
- Visor-style HUD with live fps and lag readouts
- Glide: the cursor is eased between camera frames and output at 120 Hz, so motion looks smooth instead of choppy
- Precision pointer: the cursor slows down when your hand moves slowly for fine aiming, and catches up to your fingertip when you move fast
- Sketch window: mark up a PDF with your hand (originals are never changed, marked-up copies are saved to `~/Documents/FIVES Notes`)
- Snap pens: draw a shape and hold still, and FIVES redraws it as a clean shape
- Draw mode for sketch pads and drawing apps
- Music window: a floating Spotify panel (play/pause, next/previous, seek, volume), shown or hidden with an open-palm flick
- Brain: optional local chat model that can use tools on the Mac

**Planned**
- Calendar, AI, and email windows that flick into view, so small tasks don't need new tabs
- Volume dial and keyboard shortcuts that run tools, with no model needed
- Voice commands
- Drive a 3D-printed robotic hand from the same hand tracking

## Hand mouse: gestures

Press `c` in the camera window to turn cursor control on or off. Press `h` to switch the window between the camera and a hand-only view, and `[` / `]` to turn the blue tint down or up. Press `q` to quit.

The camera window is a visor-style HUD (`hud.py`): an angled helmet frame with the camera in a viewport in the middle (natural colors with a cool blue tint, drawn at double resolution so text is sharp), your hand's wiring, a bracket on the cursor spot, the current mode, pinch gap, and live fps/lag readouts. Set `HUD = False` in `config.py` for the plain camera picture. Tuning: `HUD_STRENGTH` (blue tint), `HUD_SCALE` (1 = faster, 2 = sharper), `HUD_DENOISE`, `HUD_GLOW`.

| Gesture | What it does |
| --- | --- |
| Point with your index finger | Move the cursor |
| Pinch (thumb + index), then let go | Click. Click twice quickly for a double-click, three times for a triple-click |
| Pinch, then move your hand | Drag (windows, Chrome tabs, text) |
| Pinch and hold still for 0.4 s | Press and hold |
| Pinch with thumb + index + middle | Right click |
| Hold Cmd + Shift, then pinch and move your hand up or down | Scroll. Let go of the pinch while moving and the page keeps gliding |
| Open hand (all five fingers out), then flick it sideways | Show or hide the music window. The cursor freezes while your hand is open. Which direction hides it is set by `FLICK_HIDE` in `config.py` |
| Tap Cmd + Escape | Open the sketch window and turn draw mode on (tap again to put it away). Your hand only points; hold the pen key to put ink down, let go to lift. Pinching does nothing in this mode. Hold still at the end of a stroke to snap it into a clean shape |

While you hold Cmd + Shift, the cursor stays where it was and clicking is paused. In draw mode the pen follows your hand at half speed (`DRAW_GAIN`) through an extra smoothing filter, so small precise strokes are easier; lift, move and press again to go farther. Tap Option for a dot. Hotkeys work from any app and are set in `config.py` (`SCROLL_HOTKEY`, `DRAW_TOGGLE_HOTKEY`, `DRAW_PEN_KEY`). Set `DRAW_PEN = "pinch"` for the older pinch pen (hold Cmd + Option, then pinch).

<!-- 📍 GIF 2 (gestures): pinch-click, drag a window, Cmd+Shift scroll. -->

<!-- 📍 GIF 3 (precision pointer): aiming at something small, slow then fast. -->

### The music window

<!-- 📍 GIF 4: open-palm flick hiding and showing the music window. -->

A small frosted-glass window that floats over everything and shows the current Spotify track, cover art, and playback state. Click PREV, PLAY/PAUSE, or NEXT, click the progress or volume bars to jump or set levels, and drag along a bar to scrub. Drag empty glass to move the window and drag the bottom-right corner to resize. It controls the Spotify desktop app through AppleScript, so no account keys or logins are needed.

### The sketch window

<!-- 📍 GIF 5: Cmd+Esc opens the sketch window, draw a stroke, hold still to snap a shape. -->

### Tips

- Good, even light helps a lot.
- A pinch is easier for the camera to see from the side than head-on. Turn your hand slightly toward the camera's side.
- Slam the cursor into a screen corner to stop everything (emergency brake).

## Setup

Requires macOS and Python 3.12.

```
git clone https://github.com/yagiht/fives.git
cd fives
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python eyes.py
```

The hand-tracking model (a few MB) downloads automatically the first time you run `eyes.py`.

macOS will ask for permissions. Allow them for Terminal (or whichever app you run Python from):

- **Camera**: so FIVES can see your hand
- **Accessibility**: so it can move the mouse and click
- **Input Monitoring**: so it can notice the Cmd + Shift scroll hotkey from any app

(System Settings > Privacy & Security). Restart the program after changing a permission.

## The brain (optional)

```
ollama pull qwen3.6:35b      # one time, about 23 GB
python main.py               # type requests; it picks a tool or answers
```

The model and personality are set in `config.py`.

## Tuning

Everything adjustable is in `config.py`, with a comment next to each setting saying what to change if something feels off. Common ones:

- `PINCH_START` / `PINCH_END`: how close your fingers must be to count as a pinch
- `DRAG_DISTANCE`: how far your hand moves before a pinch becomes a drag
- `HOLD_TO_PRESS_SECONDS`: the press-and-hold delay
- `SCROLL_HOTKEY`, `SCROLL_GAIN`, `SCROLL_DIRECTION`: scroll mode (use -1 for direction if it feels backwards)
- `DRAW_PEN`, `DRAW_TOGGLE_HOTKEY`, `DRAW_PEN_KEY`, `DRAW_GAIN`, `DRAW_MIN_CUTOFF`, `DRAW_BETA`: key draw mode (`DRAW_HOTKEY`, `DRAW_HOLD_END`, `DRAW_LIFT_GUARD` are for the pinch pen)
- `DRAG_SETTLE_SECONDS`: how long the cursor holds still after you let go of a drag
- `MIN_CUTOFF` / `BETA`: cursor smoothing (steadier vs. snappier). These are the settings of a One Euro filter, which smooths heavily when your hand is nearly still and lightly when it moves fast, so it cuts jitter without adding lag
- `GLIDE`, `GLIDE_SECONDS`, `GLIDE_HZ`: glide, which eases the cursor between camera frames and outputs it at `GLIDE_HZ` (120 by default)
- `PRECISE`, `PRECISE_SPEED`, `PRECISE_MIN_SCALE`, `PRECISE_CATCHUP_SPEED`: the precision pointer. Below `PRECISE_SPEED` the cursor moves only a fraction of your hand (down to `PRECISE_MIN_SCALE`), and above `PRECISE_CATCHUP_SPEED` it snaps back under your fingertip
- `SKETCH`, `SKETCH_FOLDER`, `SKETCH_SMOOTH_PASSES`, `SKETCH_LIVE_FOLLOW`: the sketch window
- `SNAP`, `SNAP_HOLD_SECONDS`, `SNAP_HOLD_RADIUS`: hold-to-snap shapes
- `FLICK_HIDE`: which sideways flick hides the music window

## Project layout

| File | Purpose |
| --- | --- |
| `eyes.py` | Webcam loop and mouse control, including the `Glider` that smooths the cursor between camera frames |
| `hud.py` | The visor HUD drawn in the camera window (camera and hand-only views) |
| `gestures.py` | Hand geometry and logic: pinch, smoothing, click, drag, scroll, and the open-palm flick. No camera code, so it stays testable |
| `panel.py` | The floating music window |
| `panel_logic.py` | Where things are in the music window and what a click means |
| `spotify.py` | Talks to the Spotify desktop app (play/pause, skip, volume, seek) |
| `hotkey.py` | Global key listener for the scroll and draw hotkeys (and hiding the pen key) |
| `config.py` | All settings and the personality |
| `tools.py` | What FIVES can do on the Mac |
| `brain.py` | The agent loop (Ollama chat + tool calls) |
| `main.py` | Typed chat front end |

## Roadmap

- [x] Hand-tracked cursor: move, click, double-click, drag, right click, scroll
- [x] Minimalist on-screen HUD
- [x] Music window with Spotify controls and open-palm flick to show or hide
- [ ] Calendar, AI, and email windows
- [ ] Volume dial and keyboard shortcuts that run tools, with no model needed
- [ ] Voice commands
- [ ] Drive a 3D-printed robotic hand from the same hand tracking
