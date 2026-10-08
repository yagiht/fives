"""
tools.py - FIVES's hands.

Each tool is an ordinary Python function. The @tool line above it adds it to
the TOOLS list, which is the menu the brain is allowed to choose from.

The brain never sees your code. It only sees:
  - the function's name
  - its type hints (name: str, level: int)
  - its docstring (the text in triple quotes)
So write the docstring like you're explaining the tool to a new assistant.
"""

import datetime
import subprocess

TOOLS = []


def tool(fn):
    """Register a function as a tool FIVES can use."""
    TOOLS.append(fn)
    return fn


def _run(command: list) -> subprocess.CompletedProcess:
    """Run a Mac command and capture what it prints. (Not a tool: no @tool.)"""
    return subprocess.run(command, capture_output=True, text=True)


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------

@tool
def open_app(name: str) -> str:
    """Open a Mac application by name.

    Args:
        name: The app's name, for example "Safari", "Spotify", or "Notes".
    """
    result = _run(["open", "-a", name])
    if result.returncode == 0:
        return f"Opened {name}."
    return f"Couldn't open {name}: {result.stderr.strip()}"


@tool
def open_url(url: str) -> str:
    """Open a website in the default browser.

    Args:
        url: The full address, for example "https://github.com".
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    _run(["open", url])
    return f"Opened {url}."


@tool
def set_volume(level: int) -> str:
    """Set the Mac's output volume.

    Args:
        level: A whole number from 0 (silent) to 100 (max).
    """
    level = max(0, min(100, int(level)))
    _run(["osascript", "-e", f"set volume output volume {level}"])
    return f"Volume set to {level}."


@tool
def run_shortcut(name: str) -> str:
    """Run one of the user's macOS Shortcuts by its exact name.

    Args:
        name: The Shortcut's name as it appears in the Shortcuts app.
    """
    result = _run(["shortcuts", "run", name])
    if result.returncode == 0:
        return f"Ran shortcut '{name}'."
    return f"Shortcut failed: {result.stderr.strip()}"


@tool
def get_time() -> str:
    """Get the current date and time."""
    return datetime.datetime.now().strftime("It's %A, %B %d, %I:%M %p.")


@tool
def study_mode() -> str:
    """Set up the Mac for focused studying: opens Notes and Safari, lowers the volume."""
    steps = [open_app("Notes"), open_app("Safari"), set_volume(20)]
    return " ".join(steps)
