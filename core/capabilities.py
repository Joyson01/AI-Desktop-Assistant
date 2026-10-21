"""Runtime Host & Desktop Session Capability Detector for MARUTI.

Detects:
- Operating system and session type (X11, Wayland, Windows, Headless).
- Physical display availability and geometry.
- Hardware microphone enumeration and PyAudio availability.
- Tesseract OCR availability.
- Active clipboard backends (Native PySide6 vs CLI fallbacks).
- Safe input control capabilities and window focus tracking.
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
from typing import Any, Dict

from core.models import BackendCapability

logger = logging.getLogger("maruti.capabilities")


def detect_capabilities() -> BackendCapability:
    """Detect and return current desktop session capabilities."""
    system = platform.system()
    details: Dict[str, Any] = {}

    # 1. Session Type & Display
    session_env = os.environ.get("XDG_SESSION_TYPE", "").lower()
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    x11_display = os.environ.get("DISPLAY", "")

    if system == "Windows":
        session_type = "windows"
        has_display = True
    elif system == "Linux":
        if wayland_display or session_env == "wayland":
            session_type = "wayland"
            has_display = bool(x11_display or wayland_display)
        elif x11_display or session_env == "x11":
            session_type = "x11"
            has_display = bool(x11_display)
        else:
            session_type = "headless"
            has_display = False
    else:
        session_type = "macos" if system == "Darwin" else "unsupported"
        has_display = bool(x11_display)

    details["DISPLAY"] = x11_display
    details["WAYLAND_DISPLAY"] = wayland_display
    details["XDG_SESSION_TYPE"] = session_env

    # 2. PyAudio & Microphone
    has_pyaudio = False
    try:
        import pyaudio  # noqa: F401
        has_pyaudio = True
    except ImportError:
        has_pyaudio = False

    has_mic = False
    try:
        import speech_recognition as sr
        from doctor import suppress_c_stderr
        with suppress_c_stderr():
            mics = sr.Microphone.list_microphone_names()
        has_mic = bool(mics)
        details["mic_count"] = len(mics) if mics else 0
    except Exception:
        has_mic = False
        details["mic_count"] = 0

    # 3. Tesseract OCR
    tess_path = shutil.which("tesseract")
    has_tess = bool(tess_path)
    details["tesseract_path"] = tess_path

    # 4. Native Clipboard
    has_cb = False
    try:
        from core.clipboard import get_clipboard_text, set_clipboard_text
        has_cb = True
    except Exception:
        has_cb = False

    # 5. Safe Synthetic Keys & Input Injection
    # Windows native or Linux with XWayland/X11 active display
    supports_keys = (system == "Windows") or (system == "Linux" and bool(x11_display))

    # 6. Window Focus / Title Inspection
    supports_focus = (system == "Windows") or bool(shutil.which("xdotool") or shutil.which("wmctrl"))
    details["has_xdotool"] = bool(shutil.which("xdotool"))
    details["has_wmctrl"] = bool(shutil.which("wmctrl"))

    cap = BackendCapability(
        os_name=system,
        session_type=session_type,
        has_display=has_display,
        has_microphone=has_mic,
        has_pyaudio=has_pyaudio,
        has_tesseract=has_tess,
        has_native_clipboard=has_cb,
        supports_synthetic_keys=supports_keys,
        supports_window_focus_check=supports_focus,
        details=details,
    )
    logger.debug("Detected session capabilities: %s", cap)
    return cap
