from computer.clipboard import Clipboard
from computer.text_selection import find_text_target, select_text_range, select_text_target


class FakeExecutor:
    def __init__(self):
        self.actions = []

    def execute(self, action):
        self.actions.append(action)
        return {"success": True, "action": action.get("action"), "message": "ok"}


def test_find_text_target_returns_structured_match():
    matches = [
        {"text": "Hello", "bbox": {"left": 100, "top": 200, "right": 160, "bottom": 225}, "center": {"x": 130, "y": 212}, "confidence": 0.94},
        {"text": "Hello", "bbox": {"left": 300, "top": 200, "right": 360, "bottom": 225}, "center": {"x": 330, "y": 212}, "confidence": 0.90},
    ]
    result = find_text_target("Hello", matches=matches, focused_text="")
    assert result["status"] == "ambiguous"
    assert len(result["matches"]) == 2


def test_select_text_target_returns_action_payload():
    payload = select_text_target("Hello", matches=[{"text": "Hello", "bbox": {"left": 10, "top": 20, "right": 50, "bottom": 30}, "center": {"x": 30, "y": 25}, "confidence": 0.96}])
    assert payload["action"] == "select_text"
    assert payload["target"] == "Hello"


def test_select_range_returns_text_range_action():
    payload = select_text_range("Hello", "India", matches={"start": [{"text": "Hello", "center": {"x": 10, "y": 10}, "bbox": {"left": 5, "top": 5, "right": 15, "bottom": 15}, "confidence": 0.97}], "end": [{"text": "India", "center": {"x": 40, "y": 40}, "bbox": {"left": 20, "top": 20, "right": 45, "bottom": 35}, "confidence": 0.95}]})
    assert payload["action"] == "select_text_range"
    assert payload["start_text"] == "Hello"
    assert payload["end_text"] == "India"


def test_clipboard_round_trip_and_verification():
    clipboard = Clipboard()
    clipboard.write("hello")
    assert clipboard.read() == "hello"
    assert clipboard.verify_changed(previous="old") is True
    assert clipboard.verify_changed(previous="hello") is False


def test_fake_executor_tracks_copy_and_paste_actions():
    executor = FakeExecutor()
    executor.execute({"action": "copy"})
    executor.execute({"action": "paste_relative", "relation": "after", "anchor": "Hello"})
    assert executor.actions[0]["action"] == "copy"
    assert executor.actions[1]["relation"] == "after"
