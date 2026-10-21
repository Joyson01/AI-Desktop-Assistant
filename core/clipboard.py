"""Session-Aware Clipboard Manager for MARUTI Desktop Assistant.

Provides seamless clipboard operations across Linux (Wayland/X11), Windows, and macOS:
- Prefers native PySide6 QClipboard which works directly on Wayland without external CLI utilities.
- Falls back to pyperclip (xclip/wl-clipboard/win32) when available.
- Maintains in-process clipboard fallback for headless and restricted environments.
"""
from __future__ import annotations

import logging
import sys
from typing import Optional

logger = logging.getLogger("maruti.clipboard")

_in_memory_clipboard: str = ""


def get_clipboard_text() -> str:
    """Retrieve text from system clipboard with multi-tier fallback."""
    global _in_memory_clipboard

    # 1. Native PySide6 clipboard (Wayland & X11 native support)
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv if hasattr(sys, "argv") else [])
        cb = app.clipboard()
        text = cb.text()
        if text:
            _in_memory_clipboard = text
            return text
    except Exception as exc:
        logger.debug("PySide6 clipboard read skipped: %s", exc)

    # 2. Pyperclip fallback (CLI tools)
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

    # 1. Native PySide6 clipboard
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv if hasattr(sys, "argv") else [])
        cb = app.clipboard()
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

    return success
