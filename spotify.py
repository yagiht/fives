"""
spotify.py - talk to the Spotify desktop app on a Mac. No account keys or logins needed.

How: macOS lets one app drive another with AppleScript. We run tiny scripts with `osascript`
("tell application Spotify to next track"). The Spotify app has to be open and signed in.
The first time, macOS asks "Terminal wants to control Spotify": click OK.
(If you missed it: System Settings > Privacy & Security > Automation > Terminal > Spotify.)

Nothing here touches the screen. panel.py draws the window and calls these functions.
"""

import subprocess

SEP = "|||"

_STATUS_SCRIPT = f'''
if application "Spotify" is not running then return "NOTRUNNING"
tell application "Spotify"
    if player state is stopped then return "STOPPED"
    set stateText to player state as string
    set nameText to name of current track
    set artistText to artist of current track
    set posText to player position as string
    set durText to duration of current track as string
    set volText to sound volume as string
    set artText to ""
    try
        set artText to artwork url of current track
    end try
    return stateText & "{SEP}" & nameText & "{SEP}" & artistText & "{SEP}" & posText & "{SEP}" & durText & "{SEP}" & volText & "{SEP}" & artText
end tell
'''


_seen_errors = set()


def _run(script: str, timeout: float = 3.0):
    """Run one AppleScript. Returns (ok, printed text, error text)."""
    try:
        out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return False, "", str(e)
    err = out.stderr.strip()
    if out.returncode != 0 and err and err not in _seen_errors:     # tell the terminal once per kind of error
        _seen_errors.add(err)
        print("Spotify said:", err)
    return out.returncode == 0, out.stdout.strip(), err


def is_running() -> bool:
    """Is the Spotify app open? (Asked without AppleScript, so it needs no permission.)"""
    try:
        return subprocess.run(["pgrep", "-x", "Spotify"], capture_output=True).returncode == 0
    except Exception:
        return False


def _num(text: str, default: float = 0.0) -> float:
    """AppleScript prints numbers the way your Mac's language does ('12,5' in some), so accept both."""
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return default


def parse_status(text: str) -> dict:
    """Turn the status script's answer into a small dictionary.

    state: 'playing' | 'paused' | 'stopped' | 'closed'     (closed = the Spotify app isn't open)
    """
    text = (text or "").strip()
    if text == "" or text == "NOTRUNNING":
        return {"state": "closed"}
    if text == "STOPPED":
        return {"state": "stopped"}
    parts = text.split(SEP)
    if len(parts) < 6:
        return {"state": "closed"}
    duration = _num(parts[4])
    return {
        "state": parts[0].strip() if parts[0].strip() in ("playing", "paused") else "paused",
        "title": parts[1],
        "artist": parts[2],
        "position": _num(parts[3]),
        # older Spotify versions give milliseconds, newer ones seconds: a song is never over 10 hours
        "duration": duration / 1000.0 if duration > 36000 else duration,
        "volume": int(_num(parts[5], 50)),
        "art_url": parts[6].strip() if len(parts) > 6 else "",
    }


def status() -> dict:
    """state: playing / paused / stopped / closed (app not open) / error (open, but we can't talk to it)."""
    if not is_running():
        return {"state": "closed"}
    ok, out, err = _run(_STATUS_SCRIPT)
    if not ok:
        return {"state": "error", "error": err, "permission": "-1743" in err or "not authorized" in err.lower()}
    return parse_status(out)


def _tell(command: str) -> None:
    _run(f'tell application "Spotify" to {command}')


def play_pause() -> None:
    _tell("playpause")


def next_track() -> None:
    _tell("next track")


def previous_track() -> None:
    _tell("previous track")


def set_volume(percent: int) -> None:
    _tell(f"set sound volume to {max(0, min(100, int(percent)))}")


def seek(seconds: float) -> None:
    _tell(f"set player position to {max(0.0, float(seconds)):.1f}")


def quit_app() -> None:
    """Close the Spotify app (only if it's open, so this never launches it by accident)."""
    if is_running():
        _tell("pause")           # stop the sound first, so the music ends even if quitting is slow
        _tell("quit")


def open_app() -> None:
    """Launch Spotify (used when its window's button is clicked while it's closed)."""
    try:
        subprocess.Popen(["open", "-a", "Spotify"])
    except Exception:
        pass
