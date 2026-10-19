from PIL import Image

from brain.visual_brain import MockVisualBrain
from computer.action_pipeline import ActionPipeline


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, payload):
        self.calls.append(payload)
        return {"success": True, "message": "executed"}


def make_pipeline(response):
    executor = FakeExecutor()
    brain = MockVisualBrain({"test": response})
    return ActionPipeline(brain, executor), executor


def test_pipeline_forwards_click_once():
    pipeline, executor = make_pipeline({"action": "click", "x": 100, "y": 200})

    result = pipeline.run("test", Image.new("RGB", (1920, 1080)))

    assert result["success"] is True
    assert executor.calls == [{"action": "click", "target": {"x": 100, "y": 200}}]


def test_pipeline_forwards_type_press_hotkey_and_scroll():
    cases = [
        ({"action": "type", "text": "hello"}, {"action": "type", "text": "hello"}),
        ({"action": "press", "key": "enter"}, {"action": "press", "key": "enter"}),
        ({"action": "hotkey", "keys": ["ctrl", "r"]}, {"action": "hotkey", "keys": ["ctrl", "r"]}),
        ({"action": "scroll", "amount": -600}, {"action": "scroll", "amount": -600}),
    ]

    for response, expected in cases:
        pipeline, executor = make_pipeline(response)
        assert pipeline.run("test", Image.new("RGB", (1920, 1080)))["success"] is True
        assert executor.calls == [expected]


def test_pipeline_returns_done_and_ask_user_without_executor_call():
    for response in (
        {"action": "done", "message": "Task completed."},
        {"action": "ask_user", "message": "Which account?"},
    ):
        pipeline, executor = make_pipeline(response)

        result = pipeline.run("test", Image.new("RGB", (1920, 1080)))

        assert result["success"] is True
        assert result["action"] in {"done", "ask_user"}
        assert executor.calls == []


def test_pipeline_rejects_invalid_unknown_and_out_of_screen_actions():
    responses = [
        {"action": "type"},
        {"action": "run_python", "code": "print(1)"},
        {"action": "click", "x": 3000, "y": 500},
        {"action": "click", "x": -10, "y": 500},
    ]

    for response in responses:
        pipeline, executor = make_pipeline(response)
        result = pipeline.run("test", Image.new("RGB", (1920, 1080)))

        assert result["success"] is False
        assert executor.calls == []


def test_pipeline_uses_context_dimensions_without_screenshot():
    pipeline, executor = make_pipeline({"action": "click", "x": 100, "y": 200})

    result = pipeline.run("test", None, {"screen_width": 640, "screen_height": 480})

    assert result["success"] is True
    assert executor.calls