from dataclasses import dataclass
import math


ACTION_NAMES = {
    "click",
    "double_click",
    "right_click",
    "type",
    "press",
    "hotkey",
    "scroll",
    "wait",
    "done",
    "ask_user",
    "system_control",
    "copy",
    "paste",
    "paste_relative",
    "select",
    "select_all",
    "select_text",
    "select_text_range",
    "take_screenshot",
    "screenshot_start",
    "mouse_move",
    "mouse_down",
    "mouse_up",
    "caps_lock",
    "minimize_window",
    "restore_window",
    "open_application",
    "open_multiple_applications",
    "arrange_windows",
    "open_url",
}


@dataclass(frozen=True)
class Action:
    name: str
    x: float | int | None = None
    y: float | int | None = None
    text: str | None = None
    key: str | None = None
    keys: tuple[str, ...] | None = None
    amount: int | None = None
    milliseconds: int | None = None
    message: str | None = None
    target: str | None = None
    direction: str | None = None
    button: str | None = None

    @classmethod
    def from_dict(cls, payload):
        valid, message = ActionValidator.validate(payload)
        if not valid:
            raise ValueError(message)
        return cls(
            name=payload["action"],
            x=payload.get("x"),
            y=payload.get("y"),
            text=payload.get("text"),
            key=payload.get("key"),
            keys=tuple(payload["keys"]) if "keys" in payload else None,
            amount=payload.get("amount"),
            milliseconds=payload.get("milliseconds"),
            message=payload.get("message"),
            target=payload.get("target"),
            direction=payload.get("direction"),
            button=payload.get("button"),
        )

    def to_dict(self):
        payload = {"action": self.name}
        for field in ("x", "y", "text", "key", "amount", "milliseconds", "message", "target", "direction", "button"):
            value = getattr(self, field)
            if value is not None:
                payload[field] = value
        if self.keys is not None:
            payload["keys"] = list(self.keys)
        return payload


class ActionValidator:
    @staticmethod
    def validate(payload, screen_size=None):
        if not isinstance(payload, dict):
            return False, "action must be an object"
        name = payload.get("action")
        if name not in ACTION_NAMES:
            return False, "unknown action"

        if name in {"click", "double_click", "right_click"}:
            if not _valid_coordinate(payload.get("x")) or not _valid_coordinate(payload.get("y")):
                return False, "click coordinates must be finite non-negative numbers"
            if screen_size is not None and not _within_screen(payload, screen_size):
                return False, "coordinates outside screen"
        elif name == "type" and not _non_empty_string(payload.get("text")):
            return False, "type requires text"
        elif name == "press" and not _non_empty_string(payload.get("key")):
            return False, "press requires key"
        elif name == "hotkey":
            keys = payload.get("keys")
            if not isinstance(keys, list) or len(keys) < 2 or not all(_non_empty_string(key) for key in keys):
                return False, "hotkey requires a list of keys"
        elif name in {"copy", "paste", "select", "select_all"}:
            pass
        elif name in {"take_screenshot", "caps_lock", "minimize_window", "restore_window"}:
            pass
        elif name == "screenshot_start":
            pass
        elif name == "mouse_move":
            if payload.get("direction") not in {"left", "right", "up", "down"}:
                return False, "mouse_move requires a direction"
            amount = payload.get("amount")
            if amount is not None and (isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= 10000):
                return False, "mouse_move amount must be between 1 and 10000"
        elif name in {"mouse_down", "mouse_up"} and payload.get("button", "left") not in {"left", "middle", "right"}:
            return False, "mouse action requires a supported button"
        elif name == "open_application":
            if not _non_empty_string(payload.get("application")):
                return False, "open_application requires an application"
        elif name == "open_multiple_applications":
            apps = payload.get("applications")
            if not isinstance(apps, list) or not apps or not all(_non_empty_string(app) for app in apps):
                return False, "open_multiple_applications requires a list of applications"
        elif name == "arrange_windows":
            layout = payload.get("layout")
            if layout not in {"side_by_side", "vertical", "cascade"}:
                return False, "arrange_windows requires a supported layout"
        elif name == "paste_relative":
            relation = payload.get("relation")
            if relation not in {"before", "after", "between"}:
                return False, "paste_relative requires relation before, after, or between"
            if relation in {"before", "after"} and not _non_empty_string(payload.get("anchor")):
                return False, "paste_relative before/after requires anchor"
            if relation == "between" and not (_non_empty_string(payload.get("start_text")) and _non_empty_string(payload.get("end_text"))):
                return False, "paste_relative between requires start_text and end_text"
        elif name == "select_text":
            target = payload.get("target")
            if not _non_empty_string(target):
                return False, "select_text requires target"
        elif name == "select_text_range":
            start = payload.get("start_text")
            end = payload.get("end_text")
            if not _non_empty_string(start) or not _non_empty_string(end):
                return False, "select_text_range requires start_text and end_text"
        elif name == "system_control":
            target = payload.get("target")
            if not _non_empty_string(target):
                return False, "system_control requires a target"
            operation = payload.get("operation", "set")
            if operation not in {"set", "open", "toggle"}:
                return False, "system_control operation must be set, open, or toggle"
            value = payload.get("value")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                return False, "system_control value must be a string or number"
        elif name == "open_url":
            from urllib.parse import urlsplit
            parsed = urlsplit(payload.get("target", ""))
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                return False, "open_url requires a safe absolute URL"
        elif name == "scroll" and (
            isinstance(payload.get("amount"), bool)
            or not isinstance(payload.get("amount"), int)
            or payload["amount"] == 0
            or abs(payload["amount"]) > 10000
        ):
            return False, "scroll amount must be a non-zero integer within 10000"
        elif name == "wait" and (
            isinstance(payload.get("milliseconds"), bool)
            or not isinstance(payload.get("milliseconds"), int)
            or not 0 <= payload["milliseconds"] <= 60000
        ):
            return False, "wait milliseconds must be between 0 and 60000"
        elif name in {"done", "ask_user"} and not _non_empty_string(payload.get("message")):
            return False, f"{name} requires message"

        return True, "valid"


class StructuredActionAdapter:
    def __init__(self, executor):
        self.executor = executor

    def execute(self, payload):
        valid, message = ActionValidator.validate(payload)
        if not valid:
            return {"success": False, "message": message}
        action = Action.from_dict(payload)
        if action.name in {"done", "ask_user"}:
            return {"success": True, "action": action.name, "message": action.message}
        executor_payload = action.to_dict()
        if action.name in {"click", "double_click", "right_click"}:
            executor_payload["target"] = {"x": executor_payload.pop("x"), "y": executor_payload.pop("y")}
        return self.executor.execute(executor_payload)


def _non_empty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _valid_coordinate(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _within_screen(payload, screen_size):
    if (
        not isinstance(screen_size, (tuple, list))
        or len(screen_size) != 2
        or not all(isinstance(value, int) and value > 0 for value in screen_size)
    ):
        return False
    width, height = screen_size
    return payload["x"] < width and payload["y"] < height