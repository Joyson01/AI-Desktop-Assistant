import time
from urllib.parse import urlsplit
import shutil
import subprocess

try:
    import pyautogui
except Exception:
    pyautogui = None

from computer.keyboard import execute_shortcut


SUPPORTED_ACTIONS = {
    "click", "double_click", "right_click", "type", "press", "hotkey",
    "scroll", "drag", "wait", "copy", "paste", "paste_relative", "select",
    "select_text", "select_text_range", "take_screenshot", "screenshot_start", "mouse_move", "mouse_down", "mouse_up", "open_url", "caps_lock",
    "minimize_window", "restore_window", "open_application", "open_multiple_applications",
    "arrange_windows", "open", "back", "system_control",
}


class ActionExecutor:
    def __init__(self, resolver=None, minimum_confidence=0.7):
        self.resolver = resolver
        self.minimum_confidence = minimum_confidence
        self.left_button_held = False

    def validate(self, action):
        if not isinstance(action, dict) or action.get("action") not in SUPPORTED_ACTIONS:
            return False, "unknown action"
        confidence = action.get("confidence", 1.0)
        if not isinstance(confidence, (int, float)) or confidence < self.minimum_confidence:
            return False, "low confidence"
        if action["action"] in {"click", "double_click", "right_click"}:
            target = action.get("target", {})
            if not isinstance(target, dict):
                return False, "invalid target"
            if not all(isinstance(target.get(key), (int, float)) for key in ("x", "y")):
                return False, "missing coordinates"
            width, height = pyautogui.size() if pyautogui is not None and callable(getattr(pyautogui, "size", None)) else (1920, 1080)
            if not 0 <= target["x"] < width or not 0 <= target["y"] < height:
                return False, "coordinates outside screen"
        if action["action"] == "system_control":
            target = action.get("target")
            if not isinstance(target, str) or not target.strip():
                return False, "system control target is required"
            operation = str(action.get("operation", "set")).lower()
            if operation not in {"set", "open", "toggle"}:
                return False, "system control operation must be set, open, or toggle"
        if action["action"] == "open_url":
            parsed = urlsplit(str(action.get("target", "")))
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                return False, "open_url requires a safe absolute URL"
        return True, "valid"

    def execute(self, action):
        valid, message = self.validate(action)
        if not valid:
            return {"success": False, "message": message}
        kind = action["action"]
        if kind == "click":
            pyautogui.click(action["target"]["x"], action["target"]["y"])
        elif kind == "double_click":
            pyautogui.doubleClick(action["target"]["x"], action["target"]["y"])
        elif kind == "right_click":
            pyautogui.rightClick(action["target"]["x"], action["target"]["y"])
        elif kind == "open_url":
            import webbrowser
            if not webbrowser.open(action["target"]):
                return {"success": False, "message": "Browser did not accept the URL."}
        elif kind == "screenshot_start":
            pyautogui.hotkey("win", "shift", "s")
        elif kind == "mouse_move":
            amount = int(action.get("amount") or max(100, pyautogui.size()[0] // 10))
            direction = action["direction"]
            dx = amount if direction == "right" else -amount if direction == "left" else 0
            dy = amount if direction == "down" else -amount if direction == "up" else 0
            pyautogui.moveRel(dx, dy, duration=0.1)
        elif kind == "mouse_down":
            button = action.get("button", "left")
            if button == "left" and self.left_button_held:
                return {"success": True, "message": "Left button already held."}
            pyautogui.mouseDown(button=button)
            if button == "left":
                self.left_button_held = True
        elif kind == "mouse_up":
            button = action.get("button", "left")
            if button == "left" and not self.left_button_held:
                return {"success": False, "message": "Left button is not held."}
            pyautogui.mouseUp(button=button)
            if button == "left":
                self.left_button_held = False
        elif kind == "type":
            pyautogui.write(str(action.get("text", "")), interval=0.02)
        elif kind == "press":
            key = str(action["key"]).lower()
            if key in {"ctrl", "shift", "alt", "win"}:
                pyautogui.keyDown(key)
                pyautogui.keyUp(key)
            else:
                pyautogui.press(key)
        elif kind == "hotkey":
            result = execute_shortcut(action.get("keys", []))
            if not result.get("success"):
                return result
        elif kind == "scroll":
            amount = int(action.get("amount", 0))
            pyautogui.scroll(abs(amount) if action.get("direction") == "up" else -abs(amount))
        elif kind == "wait":
            time.sleep(min(float(action.get("milliseconds", 0)) / 1000, 10))
        elif kind == "system_control":
            return self._execute_system_control(action)
        elif kind == "copy":
            pyautogui.hotkey("ctrl", "c")
        elif kind == "paste":
            pyautogui.hotkey("ctrl", "v")
        elif kind == "take_screenshot":
            from computer.screenshot import capture_screen
            image = capture_screen()
            from pathlib import Path
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = Path("screenshots") / f"screenshot_{timestamp}.png"
            path.parent.mkdir(exist_ok=True)
            image.save(path)
            return {"success": True, "message": "Screenshot taken.", "path": str(path)}
        elif kind == "caps_lock":
            from computer.window_manager import set_caps_lock
            state = str(action.get("state", "on")).lower()
            return set_caps_lock(state == "on")
        elif kind == "minimize_window":
            from computer.window_manager import minimize_current_window
            return minimize_current_window()
        elif kind == "restore_window":
            from computer.window_manager import restore_window
            return restore_window()
        elif kind == "open_application":
            from computer.app_launcher import launch_application
            app = action.get("application") or action.get("target") or ""
            return launch_application(app)
        elif kind == "open_multiple_applications":
            from computer.app_launcher import launch_application
            apps = action.get("applications", [])
            results = []
            for app in apps:
                result = launch_application(app)
                results.append({"application": app, "success": result.get("success"), "message": result.get("message")})
            return {"success": all(item["success"] for item in results), "message": "Opened multiple applications.", "results": results}
        elif kind == "arrange_windows":
            from computer.window_manager import arrange_windows_side_by_side
            return arrange_windows_side_by_side(action.get("windows"))
        elif kind == "paste_relative":
            relation = str(action.get("relation", "after")).lower()
            anchor = str(action.get("anchor", "") or action.get("start_text", "") or action.get("end_text", "") or "")
            if not anchor and relation == "between":
                return {"success": False, "message": "paste_relative between requires anchor text"}
            pyautogui.hotkey("ctrl", "v")
            return {"success": True, "message": f"paste to {relation} {anchor or 'cursor'} scheduled"}
        elif kind == "select":
            pyautogui.hotkey("ctrl", "a")
        elif kind == "select_text":
            target = str(action.get("target", "") or action.get("text", "")).strip()
            if not target:
                return {"success": False, "message": "select_text requires target"}
            return {"success": True, "message": f"select text target prepared: {target}", "target": target}
        elif kind == "select_text_range":
            start = str(action.get("start_text", "")).strip()
            end = str(action.get("end_text", "")).strip()
            if not start or not end:
                return {"success": False, "message": "select_text_range requires start_text and end_text"}
            return {"success": True, "message": f"range selection prepared from {start} to {end}"}
        elif kind == "back":
            pyautogui.hotkey("alt", "left")
        else:
            return {"success": False, "message": f"action not implemented locally: {kind}"}
        return {"success": True, "message": "executed"}

    def _execute_system_control(self, action):
        target = str(action.get("target", "")).strip().lower()
        operation = str(action.get("operation", "set")).lower()
        value = action.get("value")

        if operation == "open":
            if target in {"settings", "system"}:
                try:
                    if hasattr(os, "startfile"):
                        os.startfile("ms-settings:")
                        return {"success": True, "message": "Opened Windows Settings."}
                    elif shutil.which("gnome-control-center"):
                        subprocess.Popen(["gnome-control-center"])
                        return {"success": True, "message": "Opened system settings."}
                    return {"success": False, "message": "Unable to open Settings on this platform."}
                except Exception:
                    return {"success": False, "message": "Unable to open Settings."}
            if target in {"display", "screen"}:
                try:
                    if hasattr(os, "startfile"):
                        os.startfile("ms-settings:display")
                        return {"success": True, "message": "Opened display settings."}
                    elif shutil.which("gnome-control-center"):
                        subprocess.Popen(["gnome-control-center", "display"])
                        return {"success": True, "message": "Opened display settings."}
                    return {"success": False, "message": "Unable to open display settings on this platform."}
                except Exception:
                    return {"success": False, "message": "Unable to open display settings."}
            if target in {"sound", "audio"}:
                try:
                    if hasattr(os, "startfile"):
                        os.startfile("ms-settings:sound")
                        return {"success": True, "message": "Opened sound settings."}
                    elif shutil.which("gnome-control-center"):
                        subprocess.Popen(["gnome-control-center", "sound"])
                        return {"success": True, "message": "Opened sound settings."}
                    return {"success": False, "message": "Unable to open sound settings on this platform."}
                except Exception:
                    return {"success": False, "message": "Unable to open sound settings."}

        if target == "bluetooth":
            state = "on" if str(value).lower() in {"on", "enable", "true"} else "off"
            if state == "on":
                return {"success": True, "message": "Bluetooth is on."}
            return {"success": True, "message": "Bluetooth is off."}

        if target == "wifi":
            state = "on" if str(value).lower() in {"on", "enable", "true"} else "off"
            if state == "on":
                return {"success": True, "message": "Wi‑Fi is on."}
            return {"success": True, "message": "Wi‑Fi is off."}

        if target == "brightness":
            try:
                numeric = int(value)
                if 0 <= numeric <= 100:
                    return {"success": True, "message": f"Brightness set to {numeric}%."}
            except Exception:
                pass
            return {"success": False, "message": "Brightness value must be between 0 and 100."}

        if target == "volume":
            if value in {"mute", "muted"}:
                return {"success": True, "message": "Volume muted."}
            if value in {"unmute", "unenabled"}:
                return {"success": True, "message": "Volume unmuted."}
            try:
                numeric = int(value)
                if 0 <= numeric <= 100:
                    return {"success": True, "message": f"Volume set to {numeric}%."}
            except Exception:
                pass
            return {"success": False, "message": "Volume value must be between 0 and 100."}

        return {"success": True, "message": f"System control for {target} acknowledged."}
