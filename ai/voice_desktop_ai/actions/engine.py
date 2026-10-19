import os
import shutil
import subprocess
import time
try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    from pywinauto import Desktop
except ImportError:
    Desktop = None

from computer.keyboard import execute_shortcut
from verification.verifier import state_valid

def execute(intent, before, refresh, resolve, invoke, dry_run=False, resolved_element=None):
    class Result:
        success = True
        verified = True
        message = "dry-run" if dry_run else "executed"
    if dry_run:
        if intent.action in {"click", "double_click", "right_click"}:
            print(f"DRY RUN: True; click skipped for target {intent.target!r}")
        return Result()
    if intent.action == "type": pyautogui.write(intent.value, interval=0.02)
    elif intent.action == "search":
        pyautogui.hotkey("ctrl", "l")
        pyautogui.write(intent.value, interval=0.02)
        pyautogui.press("enter")
    elif intent.action in {"click", "double_click", "right_click"}:
        element = resolved_element
        if element is None:
            element = resolve(intent.target, getattr(intent, "role", ""))
        if not element:
            return type("Result", (), {"success": False, "verified": False, "message": "target not found"})()
        try:
            click_started = time.perf_counter()
            clicked = invoke(element, intent.action)
            print(f"[PERF] mouse_click={(time.perf_counter() - click_started) * 1000:.1f}ms")
        except Exception as error:
            return type("Result", (), {"success": False, "verified": False, "message": f"click failed: {type(error).__name__}: {error}"})()
        if not clicked:
            return type("Result", (), {"success": False, "verified": False, "message": "click function failed"})()
        if callable(refresh):
            try:
                after = refresh()
            except Exception as error:
                return type("Result", (), {"success": True, "verified": False, "message": f"click verification failed: {error}"})()
            if not state_valid(after):
                return type("Result", (), {"success": True, "verified": False, "message": "click verification failed"})()
    elif intent.action == "scroll_down": pyautogui.press("pagedown")
    elif intent.action == "scroll_up": pyautogui.press("pageup")
    elif intent.action == "back": pyautogui.hotkey("alt", "left")
    elif intent.action == "forward": pyautogui.hotkey("alt", "right")
    elif intent.action == "open_tab": pyautogui.hotkey("ctrl", "t")
    elif intent.action == "close_tab": pyautogui.hotkey("ctrl", "w")
    elif intent.action == "close_window": pyautogui.hotkey("alt", "f4")
    elif intent.action == "shutdown":
        if Desktop is None:
            return type("Result", (), {"success": False, "verified": False, "message": "pywinauto is not available"})()
        desktop = Desktop(backend="uia")
        windows = desktop.windows()
        for window in windows:
            window.close()
        while desktop.windows():
            pass
        subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
    elif intent.action == "enter": pyautogui.press("enter")
    elif intent.action == "press": pyautogui.press(str(intent.value).lower())
    elif intent.action == "hotkey":
        result = execute_shortcut(intent.metadata.get("keys", []))
        if not result.get("success"):
            return type("Result", (), {"success": False, "verified": False, "message": result["message"]})()
    elif intent.action == "top": pyautogui.hotkey("ctrl", "home")
    elif intent.action == "bottom": pyautogui.hotkey("ctrl", "end")
    elif intent.action == "open" and intent.target == "chrome":
        executable = None
        if os.name == "nt":
            paths = [
                os.path.join(os.environ.get("ProgramFiles", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ]
            executable = next((path for path in paths if os.path.isfile(path)), None)
        else:
            executable = (
                shutil.which("google-chrome")
                or shutil.which("google-chrome-stable")
                or shutil.which("chromium")
                or shutil.which("chromium-browser")
            )
        if not executable:
            failure = Result()
            failure.success = False
            failure.verified = False
            failure.message = "Chrome executable not found"
            return failure
        subprocess.Popen([executable], shell=False)
        return Result()
    else:
        failure = Result()
        failure.success = False
        failure.verified = False
        failure.message = "unsupported action"
        return failure
    return Result()
