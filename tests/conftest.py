"""Global test configuration and headless environment setup for MARUTI."""
from __future__ import annotations

import os

# Ensure headless Qt doesn't attempt to connect to X11/Wayland display during unit tests
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

