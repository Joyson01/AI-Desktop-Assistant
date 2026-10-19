from brain.gemini_client import GeminiClient
from brain.intent import parse_intent
from actions.engine import execute
from computer.action_executor import ActionExecutor
from voice.speech_normalizer import normalize_command


def test_speech_normalizer_handles_hindi_hinglish_commands():
    assert normalize_command("Chrome kholo aur YouTube search karo") == "chrome aur youtube search"
    assert normalize_command("क्रोम खोलो") == "chrome"


def test_speech_normalizer_preserves_type_text():
    value = "Type print('Hello World')"
    assert normalize_command(value) == value


def test_close_chrome_command_does_not_send_window_close_hotkey(monkeypatch):
    pressed = []
    monkeypatch.setattr("actions.engine.pyautogui.hotkey", lambda *keys: pressed.append(keys))

    intent = parse_intent(normalize_command("close chorme"))
    result = execute(intent, None, lambda: None, lambda target, role: None, lambda element, action: None)

    assert intent.action == "close"
    assert intent.target == "chrome"
    assert result.success is False
    assert pressed == []


def test_close_window_command_sends_window_close_hotkey(monkeypatch):
    pressed = []
    monkeypatch.setattr("actions.engine.pyautogui.hotkey", lambda *keys: pressed.append(keys))

    intent = parse_intent(normalize_command("Close the window"))
    result = execute(intent, None, lambda: None, lambda target, role: None, lambda element, action: None)

    assert intent.action == "close_window"
    assert result.success is True
    assert pressed == [("alt", "f4")]


def test_shutdown_closes_all_windows_before_powering_off(monkeypatch):
    events = []

    class FakeWindow:
        def close(self):
            events.append("close")

    windows = [FakeWindow(), FakeWindow()]
    remaining = [windows]

    class FakeDesktop:
        def windows(self):
            events.append("list")
            return remaining.pop(0) if remaining else []

    monkeypatch.setattr("actions.engine.Desktop", lambda backend: FakeDesktop())
    monkeypatch.setattr(
        "actions.engine.subprocess.run",
        lambda *args, **kwargs: events.append(("shutdown", args, kwargs)),
    )

    intent = parse_intent(normalize_command("Shut down"))
    result = execute(intent, None, lambda: None, lambda target, role: None, lambda element, action: None)

    assert intent.action == "shutdown"
    assert result.success is True
    assert events == ["list", "close", "close", "list", ("shutdown", (["shutdown", "/s", "/t", "0"],), {"check": True})]


def test_open_new_tab_command_sends_ctrl_t_hotkey(monkeypatch):
    pressed = []
    monkeypatch.setattr("actions.engine.pyautogui.hotkey", lambda *keys: pressed.append(keys))

    intent = parse_intent(normalize_command("open new tab"))
    result = execute(intent, None, lambda: None, lambda target, role: None, lambda element, action: None)

    assert intent.action == "open_tab"
    assert result.success is True
    assert pressed == [("ctrl", "t")]


def test_close_tab_command_sends_ctrl_w_hotkey(monkeypatch):
    pressed = []
    monkeypatch.setattr("actions.engine.pyautogui.hotkey", lambda *keys: pressed.append(keys))

    intent = parse_intent(normalize_command("close tab"))
    result = execute(intent, None, lambda: None, lambda target, role: None, lambda element, action: None)

    assert intent.action == "close_tab"
    assert result.success is True
    assert pressed == [("ctrl", "w")]


def test_gemini_client_is_graceful_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = GeminiClient()
    assert client.configured is False
    assert client.analyze("test")["action"] == "ask_user"


def test_executor_rejects_unknown_and_unsafe_coordinates(monkeypatch):
    monkeypatch.setattr("computer.action_executor.pyautogui.size", lambda: (100, 100))
    executor = ActionExecutor()
    assert executor.execute({"action": "launch", "confidence": 1})["success"] is False
    assert executor.execute({
        "action": "click", "target": {"x": 101, "y": 20}, "confidence": 1,
    })["success"] is False


def test_executor_clicks_valid_coordinates(monkeypatch):
    clicked = []
    monkeypatch.setattr("computer.action_executor.pyautogui.size", lambda: (100, 100))
    monkeypatch.setattr("computer.action_executor.pyautogui.click", lambda x, y: clicked.append((x, y)))
    result = ActionExecutor().execute({
        "action": "click", "target": {"x": 20, "y": 30}, "confidence": 0.9,
    })
    assert result["success"] is True
    assert clicked == [(20, 30)]


def test_executor_tracks_left_button_hold_and_release(monkeypatch):
    calls = []
    monkeypatch.setattr("computer.action_executor.pyautogui.mouseDown", lambda **kwargs: calls.append(("down", kwargs)))
    monkeypatch.setattr("computer.action_executor.pyautogui.mouseUp", lambda **kwargs: calls.append(("up", kwargs)))
    executor = ActionExecutor()

    assert executor.execute({"action": "mouse_down", "button": "left"})["success"] is True
    assert executor.left_button_held is True
    assert executor.execute({"action": "mouse_move", "direction": "left"})["success"] is True
    assert executor.left_button_held is True
    assert executor.execute({"action": "mouse_up", "button": "left"})["success"] is True
    assert executor.left_button_held is False
    assert calls == [("down", {"button": "left"}), ("up", {"button": "left"})]
