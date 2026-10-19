import os
import sys
import unittest.mock as mock

# Ensure safe headless desktop automation during tests on Linux
if sys.platform == "linux":
    # If no display server is available, provide mock PyAutoGUI to prevent X11 socket errors
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"
    try:
        import pyautogui
    except Exception:
        mock_pg = mock.MagicMock()
        mock_pg.size.return_value = (1920, 1080)
        mock_pg.position.return_value = (100, 100)
        mock_pg.FailSafeException = type("FailSafeException", (Exception,), {})
        sys.modules["pyautogui"] = mock_pg
        sys.modules["mouseinfo"] = mock.MagicMock()

