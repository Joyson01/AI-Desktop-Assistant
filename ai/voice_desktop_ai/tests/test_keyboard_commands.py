import pytest
from unittest.mock import patch

from brain.intent import Intent
from brain.intent_router import IntentRouter
from computer import keyboard
from actions.engine import execute


@pytest.mark.parametrize(
	("transcript", "expected"),
	[
		("press ctrl+r", ["ctrl", "r"]),
		("press ctrl + r", ["ctrl", "r"]),
		("press alt+f4", ["alt", "f4"]),
		("press shift+1", ["shift", "1"]),
		("press shift+4", ["shift", "4"]),
		("press shift+,", ["shift", ","]),
		("press shift+.", ["shift", "."]),
		("press esc", ["esc"]),
		("press tab", ["tab"]),
		("press windows+r", ["win", "r"]),
		("press win+r", ["win", "r"]),
		("press alt+tab", ["alt", "tab"]),
		("press ctrl+shift+t", ["ctrl", "shift", "t"]),
		("press ctrl + shift + t", ["ctrl", "shift", "t"]),
	],
)
def test_parse_shortcut_supports_requested_key_sequences(transcript, expected):
	assert keyboard.parse_shortcut(transcript) == expected


@pytest.mark.parametrize(
	("keys", "method", "expected"),
	[
		(["esc"], "press", ("esc",)),
		(["ctrl", "r"], "hotkey", ("ctrl", "r")),
		(["shift", ","], "hotkey", ("shift", ",")),
	],
)
def test_execute_shortcut_uses_press_for_single_key_and_hotkey_for_combinations(
	monkeypatch, keys, method, expected
):
	with patch.object(keyboard.pyautogui, "press") as press, patch.object(keyboard.pyautogui, "hotkey") as hotkey:
		assert keyboard.execute_shortcut(keys)["success"] is True

		if method == "press":
			press.assert_called_once_with(*expected)
			hotkey.assert_not_called()
		else:
			hotkey.assert_called_once_with(*expected)
			press.assert_not_called()


def test_window_commands_route_to_distinct_actions():
	router = IntentRouter()

	close_window = router.route("close the window")
	switch_window = router.route("switch the window")
	close_tab = router.route("close the tab")

	assert close_window.semantic_intent == "close_window"
	assert switch_window.metadata == {"action": "hotkey", "keys": ["alt", "tab"]}
	assert close_tab.semantic_intent == "close_tab"
	assert close_tab.legacy_intent.action == "close_tab"


def test_action_engine_dispatches_single_key_without_real_input(monkeypatch):
	with patch.object(keyboard.pyautogui, "press") as press:
		result = execute(Intent("press", value="f5"), None, None, None, None)

	assert result.success is True
	press.assert_called_once_with("f5")
