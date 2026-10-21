"""System diagnostic utility for MARUTI Desktop Assistant.

Checks Python version, OS/display session type, microphone availability,
internet connectivity, Gemini API key, Tesseract OCR, PyAutoGUI, and TTS engine.
Prints a formatted report with PASS/WARN/FAIL and actionable fix hints.
"""
from __future__ import annotations

import contextlib
import logging
import os
import platform
import shutil
import socket
import sys
from dataclasses import dataclass
from typing import List

import config

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticResult:
    """Represents the outcome of an individual diagnostic check."""

    name: str
    status: str  # "PASS", "WARN", "FAIL"
    message: str
    fix_hint: str = ""


@contextlib.contextmanager
def suppress_c_stderr():
    """Suppress C-level stderr (ALSA/JACK/PulseAudio warning spam)."""
    saved_stderr = None
    null_fd = None
    try:
        null_fd = os.open(os.devnull, os.O_RDWR)
        saved_stderr = os.dup(2)
        os.dup2(null_fd, 2)
        os.close(null_fd)
        null_fd = None
        yield
    finally:
        if saved_stderr is not None:
            try:
                os.dup2(saved_stderr, 2)
                os.close(saved_stderr)
            except Exception:
                pass
        if null_fd is not None:
            try:
                os.close(null_fd)
            except Exception:
                pass


def check_python() -> DiagnosticResult:
    """Validate Python runtime version and required shims."""
    major, minor, micro = sys.version_info[:3]
    version_str = f"{major}.{minor}.{micro}"

    if major < 3 or (major == 3 and minor < 10):
        return DiagnosticResult(
            name="Python Version",
            status="FAIL",
            message=f"Python {version_str} is unsupported (minimum 3.10 required).",
            fix_hint="Upgrade to Python 3.10+ (recommended: 3.13 or 3.14).",
        )

    # For Python 3.13+, check audioop-lts requirement for SpeechRecognition
    if minor >= 13:
        try:
            import audioop  # noqa: F401
        except ImportError:
            try:
                import audioop_lts  # noqa: F401
            except ImportError:
                return DiagnosticResult(
                    name="Python Version",
                    status="WARN",
                    message=f"Python {version_str} detected, but audioop-lts is missing.",
                    fix_hint="Run: pip install audioop-lts (required by SpeechRecognition in Python 3.13+).",
                )

    return DiagnosticResult(
        name="Python Version",
        status="PASS",
        message=f"Python {version_str} ({platform.python_implementation()})",
    )


def check_os_session() -> DiagnosticResult:
    """Check operating system and display server session type."""
    os_name = platform.system()
    release = platform.release()

    if os_name == "Windows":
        return DiagnosticResult(
            name="OS & Display Session",
            status="PASS",
            message=f"Windows {release} (Native Desktop Session)",
        )

    if os_name == "Linux":
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        has_display = bool(os.environ.get("DISPLAY"))

        if session_type == "wayland":
            return DiagnosticResult(
                name="OS & Display Session",
                status="WARN",
                message=f"Linux ({release}) running Wayland session.",
                fix_hint="Wayland restricts global mouse automation and screen grabbing. "
                "For full desktop control, select 'Ubuntu on Xorg' at login or run with GDK_BACKEND=x11.",
            )

        if not has_display:
            return DiagnosticResult(
                name="OS & Display Session",
                status="WARN",
                message=f"Linux ({release}) headless / no $DISPLAY set.",
                fix_hint="Active X11 display is required for GUI and desktop clicks. Use --dry-run or run in a desktop terminal.",
            )

        return DiagnosticResult(
            name="OS & Display Session",
            status="PASS",
            message=f"Linux ({release}) on X11 ($DISPLAY={os.environ.get('DISPLAY')})",
        )

    return DiagnosticResult(
        name="OS & Display Session",
        status="WARN",
        message=f"{os_name} ({release}) - experimental platform.",
        fix_hint="MARUTI is officially supported on Ubuntu (X11) and Windows 10/11.",
    )


def check_microphone() -> DiagnosticResult:
    """Probe for audio input devices using SpeechRecognition/PyAudio."""
    try:
        import speech_recognition as sr

        with suppress_c_stderr():
            mics = sr.Microphone.list_microphone_names()

        if not mics:
            return DiagnosticResult(
                name="Microphone Input",
                status="WARN",
                message="No audio input devices enumerated by PyAudio.",
                fix_hint="Connect a USB microphone, check system sound settings, or run with --text mode.",
            )

        return DiagnosticResult(
            name="Microphone Input",
            status="PASS",
            message=f"Detected {len(mics)} audio device(s). Default: '{mics[0]}'",
        )
    except Exception as exc:
        return DiagnosticResult(
            name="Microphone Input",
            status="WARN",
            message=f"Microphone subsystem unavailable ({exc.__class__.__name__}).",
            fix_hint="Ensure PyAudio / ALSA is installed, or use --text mode for hands-free keyboard simulation.",
        )


def check_internet() -> DiagnosticResult:
    """Check network connectivity for cloud STT and Gemini features."""
    # Attempt quick DNS/TCP connection to Google public DNS
    try:
        sock = socket.create_connection(("8.8.8.8", 53), timeout=2.0)
        sock.close()
        return DiagnosticResult(
            name="Internet Connectivity",
            status="PASS",
            message="Online (Cloud STT and Gemini services reachable).",
        )
    except OSError:
        pass

    # Secondary check via HTTP head request
    try:
        import requests

        res = requests.head("https://www.google.com", timeout=2.0)
        if res.status_code < 400:
            return DiagnosticResult(
                name="Internet Connectivity",
                status="PASS",
                message="Online (HTTP connection verified).",
            )
    except Exception:
        pass

    return DiagnosticResult(
        name="Internet Connectivity",
        status="WARN",
        message="Offline (No active internet connection).",
        fix_hint="Offline rule-based router and local desktop actions will work. Cloud Gemini planner and Google Web Speech require internet.",
    )


def check_gemini_key() -> DiagnosticResult:
    """Validate presence of Gemini API key for function-calling planner."""
    api_key = config.GEMINI_API_KEY
    if api_key:
        masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
        return DiagnosticResult(
            name="Gemini API Key",
            status="PASS",
            message=f"Configured ({masked}), Model: {config.GEMINI_MODEL}",
        )

    return DiagnosticResult(
        name="Gemini API Key",
        status="WARN",
        message="GEMINI_API_KEY not configured in .env.",
        fix_hint="Add GEMINI_API_KEY to your .env file to enable Gemini function-calling planner and web search grounding.",
    )


def check_tesseract() -> DiagnosticResult:
    """Check Tesseract OCR executable for screen text understanding."""
    custom_cmd = config.TESSERACT_CMD
    if custom_cmd and os.path.isfile(custom_cmd):
        return DiagnosticResult(
            name="Tesseract OCR",
            status="PASS",
            message=f"Found custom binary: {custom_cmd}",
        )

    system_tesseract = shutil.which("tesseract")
    if system_tesseract:
        return DiagnosticResult(
            name="Tesseract OCR",
            status="PASS",
            message=f"Found on PATH: {system_tesseract}",
        )

    return DiagnosticResult(
        name="Tesseract OCR",
        status="WARN",
        message="Tesseract OCR binary not found.",
        fix_hint="Linux: sudo apt install tesseract-ocr | Windows: install from UB-Mannheim/tesseract/wiki and set TESSERACT_CMD in .env.",
    )


def check_pyautogui() -> DiagnosticResult:
    """Validate PyAutoGUI desktop control and display interaction."""
    try:
        import pyautogui

        w, h = pyautogui.size()
        return DiagnosticResult(
            name="PyAutoGUI Automation",
            status="PASS",
            message=f"Display initialized at {w}x{h} resolution.",
        )
    except Exception as exc:
        return DiagnosticResult(
            name="PyAutoGUI Automation",
            status="WARN",
            message=f"PyAutoGUI display interaction unavailable ({exc}).",
            fix_hint="Ensure an X11 or Windows desktop session is active. You can still test actions safely with --dry-run.",
        )


def check_tts() -> DiagnosticResult:
    """Check availability of Text-to-Speech synthesis engines."""
    available_engines: List[str] = []

    if platform.system() == "Linux":
        if shutil.which("spd-say"):
            available_engines.append("spd-say (speech-dispatcher)")
        if shutil.which("espeak-ng"):
            available_engines.append("espeak-ng")
        elif shutil.which("espeak"):
            available_engines.append("espeak")

    try:
        import pyttsx3

        engine = pyttsx3.init()
        available_engines.append(f"pyttsx3 ({engine.__class__.__name__})")
        del engine
    except Exception:
        pass

    if available_engines:
        return DiagnosticResult(
            name="Text-to-Speech (TTS)",
            status="PASS",
            message=f"Available: {', '.join(available_engines)}",
        )

    return DiagnosticResult(
        name="Text-to-Speech (TTS)",
        status="WARN",
        message="No native TTS synthesizer found.",
        fix_hint="Linux: sudo apt install speech-dispatcher espeak-ng | Windows: SAPI5 is built-in. Console fallback will be used.",
    )


def check_clipboard() -> DiagnosticResult:
    """Validate system clipboard functionality."""
    try:
        from core.clipboard import get_clipboard_text, set_clipboard_text
        test_str = "MARUTI_DOCTOR_TEST"
        ok = set_clipboard_text(test_str)
        retrieved = get_clipboard_text()
        if ok and retrieved == test_str:
            backend = "PySide6 QClipboard (Wayland/X11 native)"
            return DiagnosticResult(
                name="Clipboard Backend",
                status="PASS",
                message=f"Clipboard read/write verified ({backend}).",
            )
        return DiagnosticResult(
            name="Clipboard Backend",
            status="WARN",
            message="Clipboard backend returned partial response.",
            fix_hint="Ensure a graphical session is active.",
        )
    except Exception as exc:
        return DiagnosticResult(
            name="Clipboard Backend",
            status="WARN",
            message=f"Clipboard unavailable ({exc}).",
            fix_hint="Install wl-clipboard on Wayland or xclip on X11 if native clipboard fails.",
        )


def check_text_editor() -> DiagnosticResult:
    """Verify presence of installed desktop text editor."""
    import shutil
    import platform
    if platform.system() == "Windows":
        return DiagnosticResult(
            name="Text Editor",
            status="PASS",
            message="Notepad is built into Windows.",
        )
    for ed in ("gnome-text-editor", "gedit", "kate", "mousepad", "xed"):
        path = shutil.which(ed)
        if path:
            return DiagnosticResult(
                name="Text Editor",
                status="PASS",
                message=f"Found default editor on PATH: {path}",
            )
    return DiagnosticResult(
        name="Text Editor",
        status="WARN",
        message="No standard GNOME/Linux text editor found.",
        fix_hint="Run: sudo apt install gnome-text-editor or gedit.",
    )


def run_diagnostics() -> List[DiagnosticResult]:
    """Execute all diagnostic checks and return structured results."""
    return [
        check_python(),
        check_os_session(),
        check_microphone(),
        check_internet(),
        check_gemini_key(),
        check_tesseract(),
        check_pyautogui(),
        check_tts(),
        check_clipboard(),
        check_text_editor(),
    ]


def print_doctor_report() -> bool:
    """Print a clean diagnostic report to terminal.

    Returns:
        bool: True if no hard FAIL status was encountered.
    """
    results = run_diagnostics()

    print("\n" + "=" * 70)
    print("  MARUTI SYSTEM DOCTOR - DIAGNOSTIC CHECKLIST")
    print("=" * 70)

    pass_count = 0
    warn_count = 0
    fail_count = 0

    status_badges = {
        "PASS": "\033[92m[PASS]\033[0m",
        "WARN": "\033[93m[WARN]\033[0m",
        "FAIL": "\033[91m[FAIL]\033[0m",
    }

    # Fallback to plain text badges if colors unsupported
    plain_badges = {
        "PASS": "[PASS]",
        "WARN": "[WARN]",
        "FAIL": "[FAIL]",
    }

    use_color = sys.stdout.isatty() and platform.system() != "Windows"
    badges = status_badges if use_color else plain_badges

    for res in results:
        badge = badges.get(res.status, f"[{res.status}]")
        print(f"\n{badge} {res.name}")
        print(f"       Details: {res.message}")
        if res.fix_hint:
            print(f"       Hint:    {res.fix_hint}")

        if res.status == "PASS":
            pass_count += 1
        elif res.status == "WARN":
            warn_count += 1
        elif res.status == "FAIL":
            fail_count += 1

    print("\n" + "-" * 70)
    print(
        f"Summary: {pass_count} passed, {warn_count} warnings, {fail_count} failures."
    )

    if fail_count > 0:
        print(
            "Status: CRITICAL ISSUES DETECTED. Please resolve failures before running."
        )
        print("=" * 70 + "\n")
        return False

    if warn_count > 0:
        print(
            "Status: OPERATIONAL WITH DEGRADATION. Core local features will function."
        )
    else:
        print("Status: ALL SYSTEMS READY FOR ADVANCED CAPSTONE DEMO.")

    print("=" * 70 + "\n")
    return True


if __name__ == "__main__":
    success = print_doctor_report()
    sys.exit(0 if success else 1)
