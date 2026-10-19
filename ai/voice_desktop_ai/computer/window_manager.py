import ctypes
import os
import pyautogui


try:
    from pywinauto import Desktop
except ImportError:  # pragma: no cover
    Desktop = None


def _foreground_window_handle():
    try:
        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return None


def minimize_current_window():
    handle = _foreground_window_handle()
    if handle is None:
        return {"success": False, "message": "No active window found."}
    try:
        ctypes.windll.user32.ShowWindow(handle, 6)
        return {"success": True, "message": "Window minimized."}
    except Exception as exc:
        return {"success": False, "message": f"Could not minimize window: {exc}"}


def restore_window():
    handle = _foreground_window_handle()
    if handle is None:
        return {"success": False, "message": "No active window found."}
    try:
        ctypes.windll.user32.ShowWindow(handle, 9)
        return {"success": True, "message": "Window restored."}
    except Exception as exc:
        return {"success": False, "message": f"Could not restore window: {exc}"}


def is_caps_lock_on():
    try:
        return bool(ctypes.windll.user32.GetKeyState(0x14) & 0x0001)
    except Exception:
        return False


def set_caps_lock(on):
    current = is_caps_lock_on()
    if current == bool(on):
        return {"success": True, "message": f"Caps Lock is already {'on' if on else 'off'}."}
    try:
        pyautogui.press("capslock")
        return {"success": True, "message": f"Caps Lock turned {'on' if on else 'off'}."}
    except Exception as exc:
        return {"success": False, "message": f"Could not change Caps Lock: {exc}"}


def arrange_windows_side_by_side(window_names=None):
    if Desktop is None:
        return {"success": False, "message": "pywinauto not available."}
    try:
        desktop = Desktop(backend="uia")
        windows = [w for w in desktop.windows() if w.is_visible()]
        if not windows:
            return {"success": False, "message": "No visible windows found."}
        width = pyautogui.size()[0]
        for index, window in enumerate(windows[:2]):
            rect = window.rectangle()
            left = int(index * (width / 2))
            top = 0
            window.move_window(left=left, top=top, width=int(width / 2), height=max(rect.height, 400))
        return {"success": True, "message": "Windows arranged side by side."}
    except Exception as exc:
        return {"success": False, "message": f"Could not arrange windows: {exc}"}
