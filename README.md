# FIVES

A personal assistant for my Mac, in the spirit of Jarvis and Friday. This project has two parts:

- **Eyes** (`eyes.py`): the webcam watches my hand and turns it into a mouse. Point to move, pinch to click, drag, scroll.
- **Brain** (`main.py`): a chat front end for a local language model (run through [Ollama](https://ollama.com)) that can use tools on the Mac.

The long-term goal is for the same hand tracking to drive a 3D-printed, gesture-controlled robotic hand (501st Legion clone trooper style).

> Work in progress. Built as a learning project, one feature at a time.

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
| Hold **Cmd + Shift**, then pinch and move your hand up or down | Scroll. Let go of the pinch while moving and the page keeps gliding |
| Tap **Cmd + Escape** | Toggle draw mode on/off. Your hand only points; **hold either Option key** to put ink down, let go to lift. Pinching does nothing in this mode. For sketch pads and drawing apps |

While you hold Cmd + Shift, the cursor stays where it was and clicking is paused. In draw mode the pen follows your hand at half speed (`DRAW_GAIN`) through an extra smoothing filter, so small precise strokes are easier; lift, move and press again to go farther. Tap Option for a dot. Hotkeys work from any app and are set in `config.py` (`SCROLL_HOTKEY`, `DRAW_TOGGLE_HOTKEY`, `DRAW_PEN_KEY`). Set `DRAW_PEN = "pinch"` for the older pinch pen (hold Cmd + Option, then pinch).

Tips:
- Good, even light helps a lot.
- A pinch is easier for the camera to see from the side than head-on. Turn your hand slightly toward the camera's side.
- Slam the cursor into a screen corner to stop everything (emergency brake).

## Setup

Requires macOS and Python 3.12.

```bash
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

```bash
ollama pull qwen3.6:35b      # one time, about 23 GB
python main.py               # type requests; it picks a tool or answers
```

The model and personality are set in `config.py`.

## Tuning

Everything adjustable is in `config.py`, with a comment next to each setting saying what to change if something feels off. Common ones:

- `PINCH_START` / `PINCH_END`: how close your fingers must be to count as a pinch
- `DRAG_DISTANCE`: how far your hand moves before a pinch becomes a drag
- `HOLD_TO_PRESS_SECONDS`: the press-and-hold delay
- `SCROLL_HOTKEY`, `SCROLL_GAIN`, `SCROLL_DIRECTION`: scroll mode (use `-1` for direction if it feels backwards)
- `DRAW_PEN`, `DRAW_TOGGLE_HOTKEY`, `DRAW_PEN_KEY`, `DRAW_GAIN`, `DRAW_MIN_CUTOFF`, `DRAW_BETA`: key draw mode (`DRAW_HOTKEY`, `DRAW_HOLD_END`, `DRAW_LIFT_GUARD` are for the pinch pen)
- `DRAG_SETTLE_SECONDS`: how long the cursor holds still after you let go of a drag
- `MIN_CUTOFF` / `BETA`: cursor smoothing (steadier vs. snappier)

## Project layout

| File | Purpose |
| --- | --- |
| `eyes.py` | Webcam loop and mouse control |
| `hud.py` | The visor HUD drawn in the camera window (camera and hand-only views) |
| `gestures.py` | Hand geometry and logic: pinch, smoothing, click, drag, and scroll. No camera code, so it stays testable |
| `hotkey.py` | Global key listener for the scroll and draw hotkeys (and hiding the pen key) |
| `config.py` | All settings and the personality |
| `tools.py` | What FIVES can do on the Mac |
| `brain.py` | The agent loop (Ollama chat + tool calls) |
| `main.py` | Typed chat front end |

## Roadmap

- [x] Hand-tracked cursor: move, click, double-click, drag, right click, scroll
- [ ] Minimalist on-screen HUD
- [ ] Volume dial and keyboard shortcuts that run tools, with no model needed
- [ ] Voice commands
- [ ] Drive a 3D-printed robotic hand from the same hand tracking
