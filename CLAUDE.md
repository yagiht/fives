# FIVES

FIVES is Hoyu's personal Jarvis-style assistant for his Mac, built as a learning project.
Long-term it also drives a 3D-printed robotic hand. This is v0.2.

## The person you're working with

- Hoyu is learning to code through this project. He knows some Python and Java and is comfortable with Git.
- Explain from zero: what a change does, why, and which file it touches. No unexplained jargon.
- Work in small steps. One feature per change. Never rewrite a whole file when a few lines will do.
- He wants to understand every line he commits. After a change, give a short plain-English summary.

## Layout

- `config.py`: every setting and the personality. New settings go HERE, never hard-coded elsewhere.
- `tools.py`: what FIVES can do. Each tool is a function with `@tool`, type hints, and a Google-style
  docstring (`Args:` section). The docstring is what the model reads, so write it for the model.
- `brain.py`: the agent loop (Ollama chat + tool calls). Change rarely.
- `main.py`: typed chat front end.
- `eyes.py`: webcam hand tracking with MediaPipe, cursor control.
- `gestures.py`: pure geometry (pinch, smoothing, screen mapping). No camera or OpenCV imports here,
  so it stays testable on its own.

## Commands

```bash
source .venv/bin/activate     # always first
python main.py                # talk to FIVES (needs the Ollama app running)
python eyes.py                # hand tracking: q quits, c toggles cursor control
ollama list                   # models available locally
```

## Rules

- Python 3.12 in `.venv`. Add new packages to `requirements.txt`.
- macOS only. Tools use `open`, `osascript`, `shortcuts`, and `say`.
- MediaPipe: use the Tasks API (`mp.tasks.vision.HandLandmarker`). `mp.solutions` does not exist in
  MediaPipe 1.0. Don't follow old tutorials that use it.
- Never add a tool that runs arbitrary shell commands or deletes files.
- Tools return a short sentence saying what happened. They should not raise; return the error text instead.
- Test a new tool's shell command by hand first, then wrap it.
