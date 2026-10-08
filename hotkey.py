"""
hotkey.py - notice when you hold a key combo, even when another app is in front.

Why a separate file: eyes.py's camera window only hears keys while IT is the
front window. If you're clicking around in Chrome, Chrome gets your keystrokes.
A "global" listener hears every key press on the Mac, whatever app is in front.

HotkeyWatcher(["cmd", "shift"]).down  ->  True while Command AND Shift are both held.

It only LISTENS. It never blocks keys, so holding Command + Shift does exactly
what it always did, and nothing else. (That is why we use modifier keys alone,
with no letter: no app reacts to Command + Shift by itself.)

The first time, macOS asks for permission: System Settings > Privacy & Security >
Input Monitoring > turn on Terminal (or the app you run Python from), then restart.
"""

# Each name you can use in config.SCROLL_HOTKEY, and the keys that count for it.
# (Left and right versions of a key both count.)
KEY_GROUPS = {
    "cmd": ("cmd", "cmd_l", "cmd_r"),
    "shift": ("shift", "shift_l", "shift_r"),
    "ctrl": ("ctrl", "ctrl_l", "ctrl_r"),
    "alt": ("alt", "alt_l", "alt_r", "alt_gr"),     # "alt" is the Option key on a Mac
    "option": ("alt", "alt_l", "alt_r", "alt_gr"),
}


class HotkeyWatcher:
    def __init__(self, names):
        unknown = [n for n in names if n not in KEY_GROUPS]
        if unknown:
            raise ValueError(f"Unknown key {unknown}. Use any of: {', '.join(KEY_GROUPS)}")
        self.names = list(names)
        self.held = set()          # the key names that are down right now
        self.listener = None
        self.ok = False

    @property
    def down(self) -> bool:
        """True while every key in the combo is held."""
        return self.ok and all(any(k in self.held for k in KEY_GROUPS[n]) for n in self.names)

    def start(self) -> bool:
        """Start listening in the background. Returns False (and says why) if it can't."""
        try:
            from pynput import keyboard
        except ImportError:
            print("Hotkey off: run  pip install pynput  to hold-to-scroll from any app.")
            return False

        def name_of(key) -> str:
            return getattr(key, "name", None) or ""

        def on_press(key):
            self.held.add(name_of(key))

        def on_release(key):
            self.held.discard(name_of(key))

        try:
            self.listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self.listener.daemon = True
            self.listener.start()
        except Exception as problem:      # e.g. permission refused
            print(f"Hotkey off: {problem}")
            return False
        self.ok = True
        return True

    def stop(self) -> None:
        if self.listener is not None:
            self.listener.stop()
        self.ok = False
        self.held.clear()
