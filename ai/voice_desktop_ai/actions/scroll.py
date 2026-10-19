"""Scroll action helpers."""
try:
    import pyautogui
except Exception:
    pyautogui = None


def scroll(amount: int, direction: str = "down") -> bool:
    if pyautogui is None:
        return False
    try:
        pyautogui.scroll(-abs(amount) if direction == "down" else abs(amount))
        return True
    except Exception:
        return False

