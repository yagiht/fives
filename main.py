"""
main.py - talk to FIVES by typing.   Run:  python main.py
"""

import subprocess

import config
from brain import new_conversation, think


def speak(text: str) -> None:
    """Read text out loud with the Mac's built-in voice (if turned on in config)."""
    if config.SPEAK_REPLIES and text:
        subprocess.run(["say", "-v", config.VOICE, "-r", str(config.SPEECH_RATE), text])


def show_tool(name, args, result):
    print(f"   [tool] {name}({args}) -> {result}")


def main() -> None:
    print(f"{config.NAME} online ({config.MODEL}). Type a request, or 'quit'.")
    messages = new_conversation()

    while True:
        try:
            text = input("\nyou > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in {"quit", "exit"}:
            break
        if text.lower() == "reset":
            messages = new_conversation()
            print("(memory cleared)")
            continue
        if not text:
            continue

        reply = think(messages, text, on_tool=show_tool)
        print(f"{config.NAME.lower()} > {reply}")
        speak(reply)

    print(f"{config.NAME} offline.")


if __name__ == "__main__":
    main()
