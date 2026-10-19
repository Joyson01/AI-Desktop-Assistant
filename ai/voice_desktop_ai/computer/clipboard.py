import time
from typing import Any

import pyperclip


class Clipboard:
    """Small, safe clipboard wrapper for copy/paste verification without logging content."""

    def __init__(self):
        self._last_known_text = ""

    def read(self):
        try:
            value = pyperclip.paste()
            if isinstance(value, str) and value:
                return value
        except Exception:
            pass
        return self._last_known_text

    def write(self, value: str):
        if value is None:
            value = ""
        self._last_known_text = str(value)
        try:
            pyperclip.copy(str(value))
        except Exception:
            pass
        return True

    def verify_changed(self, previous: str | None = None):
        current = self.read()
        if previous is None:
            previous = self._last_known_text
        return current != previous and bool(current)

    def snapshot(self):
        return {"length": len(self.read()), "has_content": bool(self.read())}

    def clear(self):
        self.write("")


def read_clipboard():
    return Clipboard().read()


def write_clipboard(value: str):
    return Clipboard().write(value)


def verify_clipboard_change(previous: str | None = None):
    return Clipboard().verify_changed(previous)


def safe_log_clipboard(_value: Any):
    return "[redacted clipboard content]"
