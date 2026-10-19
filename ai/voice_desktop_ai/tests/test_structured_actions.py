from computer.actions import Action, ActionValidator, StructuredActionAdapter


def test_valid_actions_are_accepted():
    actions = [
        {"action": "click", "x": 500, "y": 300},
        {"action": "type", "text": "Saiyaara"},
        {"action": "press", "key": "enter"},
        {"action": "hotkey", "keys": ["ctrl", "r"]},
        {"action": "scroll", "amount": -600},
        {"action": "wait", "milliseconds": 1000},
        {"action": "done", "message": "Task completed."},
        {"action": "ask_user", "message": "Which account should I select?"},
    ]

    assert all(ActionValidator.validate(action)[0] for action in actions)


def test_action_round_trip_preserves_structured_fields():
    payload = {"action": "hotkey", "keys": ["ctrl", "r"]}

    assert Action.from_dict(payload).to_dict() == payload


def test_invalid_actions_are_rejected():
    invalid_actions = [
        {},
        {"action": "launch"},
        {"action": "click", "x": -1, "y": 10},
        {"action": "click", "x": float("nan"), "y": 10},
        {"action": "type"},
        {"action": "press"},
        {"action": "hotkey", "keys": "ctrl+r"},
        {"action": "hotkey", "keys": ["ctrl", ""]},
        {"action": "scroll", "amount": 0},
        {"action": "scroll", "amount": "600"},
        {"action": "wait", "milliseconds": 60001},
        {"action": "done"},
        {"action": "ask_user", "message": ""},
        "python os.remove('important.txt')",
    ]

    assert all(not ActionValidator.validate(action)[0] for action in invalid_actions)


def test_adapter_translates_click_and_does_not_execute_terminal_actions():
    calls = []

    class FakeExecutor:
        def execute(self, payload):
            calls.append(payload)
            return {"success": True, "message": "executed"}

    adapter = StructuredActionAdapter(FakeExecutor())

    assert adapter.execute({"action": "click", "x": 20, "y": 30})["success"] is True
    assert calls == [{"action": "click", "target": {"x": 20, "y": 30}}]
    assert adapter.execute({"action": "done", "message": "Finished"}) == {
        "success": True,
        "action": "done",
        "message": "Finished",
    }
    assert len(calls) == 1