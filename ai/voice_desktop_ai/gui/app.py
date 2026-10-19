"""
MARUTI GUI Application Launcher.
Initializes QApplication, configures platform hints, and runs MarutiMainWindow.
"""

import os

# Prevent Snap environments from leaking mismatched schemas
os.environ.pop("GSETTINGS_SCHEMA_DIR", None)
if "XDG_DATA_DIRS" in os.environ and "snap/code" in os.environ["XDG_DATA_DIRS"]:
    _cleaned_dirs = [d for d in os.environ["XDG_DATA_DIRS"].split(":") if "snap/code" not in d]
    os.environ["XDG_DATA_DIRS"] = ":".join(_cleaned_dirs) or "/usr/local/share/:/usr/share/:/var/lib/snapd/desktop"

os.environ.setdefault("QT_QPA_PLATFORMTHEME", "xdgdesktopportal")
os.environ.setdefault("QT_STYLE_OVERRIDE", "Fusion")
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from assistant import AccessibilityAssistant
from gui.main_window import MarutiMainWindow


def run_gui(assistant=None) -> int:
    """Launch the MARUTI PySide6 Graphical User Interface."""
    # Ensure high DPI attributes if needed
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName("MARUTI Assistant")
    app.setApplicationDisplayName("MARUTI — AI Voice Controlled Desktop Assistant")

    if assistant is None:
        assistant = AccessibilityAssistant()

    window = MarutiMainWindow(assistant=assistant)
    window.show()

    # Allow Python to catch SIGINT / Ctrl+C in terminal
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())

