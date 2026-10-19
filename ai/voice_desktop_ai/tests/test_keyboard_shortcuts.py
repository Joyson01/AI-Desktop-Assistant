from brain.intent_router import IntentRouter
from brain.smart_brain import SmartBrain
from computer.action_executor import ActionExecutor
from computer.keyboard import execute_shortcut, parse_shortcut


class FakePyAutoGUI:
    def __init__(self):
        self.events = []

    def keyDown(self, key):
        self.events.append(("down", key))

    def keyUp(self, key):
        self.events.append(("up", key))

    def press(self, key):
        self.events.append(("press", key))

    def hotkey(self, *keys):
        self.events.append(("hotkey", tuple(keys)))


def test_parse_shortcut_variants():
    assert parse_shortcut("Press Ctrl A") == ["ctrl", "a"]
    assert parse_shortcut("Control plus A") == ["ctrl", "a"]
    assert parse_shortcut("Ctrl aur A press karo") == ["ctrl", "a"]
    assert parse_shortcut("Ctrl + Shift + S") == ["ctrl", "shift", "s"]
    assert parse_shortcut("Shift + 2") == ["shift", "2"]
    assert parse_shortcut("कंट्रोल + ए") == ["ctrl", "a"]


def test_execute_shortcut_uses_real_modifier_sequence(monkeypatch):
    fake = FakePyAutoGUI()
    monkeypatch.setattr("computer.keyboard.pyautogui", fake)

    execute_shortcut(["ctrl", "shift", "s"])
    execute_shortcut(["shift", "2"])

    assert ("hotkey", ("ctrl", "shift", "s")) in fake.events
    assert ("hotkey", ("shift", "2")) in fake.events


def test_keyboard_examples_parse_to_press_or_hotkey_actions():
    router = IntentRouter()

    single_key_cases = {
        "press escape button": "esc",
        "press F4": "f4",
    }
    for text, key in single_key_cases.items():
        result = router.route(text)
        assert result.metadata == {"action": "press", "key": key, "raw_text": text.lower()}

    combination_cases = {
        "press alt + f4": ["alt", "f4"],
        "press window plus r": ["win", "r"],
        "press ctrl + shift + s": ["ctrl", "shift", "s"],
    }
    for text, keys in combination_cases.items():
        result = router.route(text)
        assert result.metadata["action"] == "hotkey"
        assert result.metadata["keys"] == keys
        assert isinstance(result.metadata["keys"], list)


def test_keyboard_examples_execute_with_mocked_pyautogui(monkeypatch):
    fake = FakePyAutoGUI()
    monkeypatch.setattr("computer.keyboard.pyautogui", fake)
    monkeypatch.setattr("computer.action_executor.pyautogui", fake)
    router = IntentRouter()
    executor = ActionExecutor()

    for text in ["press escape button", "press F4", "press alt + f4", "press window plus r", "press ctrl + shift + s"]:
        result = router.route(text)
        execution = executor.execute(result.metadata)
        assert execution["success"], text

    assert ("press", "esc") in fake.events
    assert ("press", "f4") in fake.events
    assert ("hotkey", ("alt", "f4")) in fake.events
    assert ("hotkey", ("win", "r")) in fake.events
    assert ("hotkey", ("ctrl", "shift", "s")) in fake.events


def test_fn_combinations_are_preserved_but_report_hardware_limitation(monkeypatch):
    fake = FakePyAutoGUI()
    monkeypatch.setattr("computer.keyboard.pyautogui", fake)

    result = IntentRouter().route("press fn plus f1")
    assert result.metadata["action"] == "hotkey"
    assert result.metadata["keys"] == ["fn", "f1"]

    execution = ActionExecutor().execute(result.metadata)
    assert execution["success"] is False
    assert "keyboard firmware" in execution["message"]
    assert fake.events == []


def test_router_detects_keyboard_and_selection_commands():
    router = IntentRouter()

    select_all_variants = ["Select all", "Sab select karo", "Pura select karo", "Select everything"]
    for text in select_all_variants:
        result = router.route(text)
        assert result.route == "computer_action"
        assert result.semantic_intent == "select_all"

    for text in ["Copy", "Cut", "Paste", "Press Ctrl A"]:
        result = router.route(text)
        assert result.route == "computer_action"
        assert result.semantic_intent in {"copy", "cut", "paste", "keyboard_shortcut", "select_all"}

    result = router.route("Select from hello to India")
    assert result.route == "computer_action"
    assert result.semantic_intent == "select_text_range"
    assert result.metadata["start_text"] == "hello"
    assert result.metadata["end_text"] == "india"


def test_router_detects_next_window_variants_as_alt_tab():
    router = IntentRouter()

    for text in [
        "switch to next window",
        "switch on next window",
        "next window",
        "go to next window",
    ]:
        result = router.route(text)
        assert result.route == "computer_action"
        assert result.semantic_intent == "next_window"
        assert result.metadata == {"action": "hotkey", "keys": ["alt", "tab"]}
        assert SmartBrain(router).decide(text).mode == "fast_local"


def test_next_window_executes_alt_tab_with_mocked_keyboard(monkeypatch):
    fake = FakePyAutoGUI()
    monkeypatch.setattr("computer.keyboard.pyautogui", fake)

    result = IntentRouter().route("next window")
    execution = ActionExecutor().execute(result.metadata)

    assert execution["success"]
    assert fake.events == [("hotkey", ("alt", "tab"))]
