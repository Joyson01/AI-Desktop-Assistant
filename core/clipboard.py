"""Session-Aware Clipboard Manager for MARUTI Desktop Assistant.

Provides seamless clipboard operations across Linux (Wayland/X11), Windows, and macOS:
- Safely uses active PySide6 QClipboard if a GUI application is running.
- Falls back to pyperclip (xclip/wl-clipboard/win32) for CLI and script workflows.
- Maintains in-process clipboard fallback for headless and restricted environments.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("maruti.clipboard")

_in_memory_clipboard: str = ""


def get_clipboard_text() -> str:
    """Retrieve text from system clipboard with multi-tier fallback."""
    global _in_memory_clipboard

    # 1. Native PySide6 clipboard if a Qt application is already running
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            cb = app.clipboard()
            if cb:
                text = cb.text()
                if text:
                    _in_memory_clipboard = text
                    return text
    except Exception as exc:
        logger.debug("PySide6 clipboard read skipped: %s", exc)

    # 2. Pyperclip fallback (CLI tools: wl-clipboard / xclip / win32)
    try:
        import pyperclip

        text = pyperclip.paste()
        if text:
            _in_memory_clipboard = text
            return text
    except Exception as exc:
        logger.debug("Pyperclip paste skipped: %s", exc)

    return _in_memory_clipboard


def set_clipboard_text(text: str) -> bool:
    """Copy text to system clipboard with multi-tier fallback."""
    global _in_memory_clipboard
    _in_memory_clipboard = text
    success = False

    # 1. Native PySide6 clipboard if a Qt application is already running
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            cb = app.clipboard()
            if cb:
                cb.setText(text)
                success = True
    except Exception as exc:
        logger.debug("PySide6 clipboard write skipped: %s", exc)

    # 2. Pyperclip fallback
    try:
        import pyperclip

        pyperclip.copy(text)
        success = True
    except Exception as exc:
        logger.debug("Pyperclip copy skipped: %s", exc)

    # In-memory clipboard always succeeds as fallback
    return True
