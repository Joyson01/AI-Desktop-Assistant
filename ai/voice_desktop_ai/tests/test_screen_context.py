from dataclasses import FrozenInstanceError

from PIL import Image
import pytest

from brain.screen_context import BrainInput, ScreenContext
from brain.task_orchestrator import TaskOrchestrator
from brain.visual_brain import MockVisualBrain


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, payload):
        self.calls.append(payload)
        return {"success": True, "message": "executed"}


def test_screen_context_derives_dimensions_and_is_immutable():
    image = Image.new("RGB", (640, 480))
    screen = ScreenContext(image)
    brain_input = BrainInput("goal", screen)

    assert (screen.width, screen.height) == (640, 480)
    assert screen.to_metadata()["ocr_text"] == []
    with pytest.raises(FrozenInstanceError):
        screen.width = 10
    with pytest.raises(FrozenInstanceError):
        brain_input.goal = "changed"


def test_orchestrator_passes_new_screen_and_accumulated_history_each_call():
    images = [Image.new("RGB", (800, 600), color) for color in ("red", "green", "blue")]
    observed = iter(images)
    executor = FakeExecutor()
    brain = MockVisualBrain({"goal": [
        {"action": "click", "x": 100, "y": 200},
        {"action": "click", "x": 120, "y": 220},
        {"action": "done", "message": "Finished"},
    ]})
    orchestrator = TaskOrchestrator(
        brain,
        executor,
        lambda: next(observed),
        verifier=lambda before, after, action, result, state: "success",
    )

    state = orchestrator.run("goal")

    assert state.status == "completed"
    assert [request["screenshot"] for request in brain.requests] == images
    assert brain.requests[0]["history"] == []
    assert brain.requests[1]["history"] == [{"action": "click", "x": 100, "y": 200}]
    assert brain.requests[2]["history"] == [
        {"action": "click", "x": 100, "y": 200},
        {"action": "click", "x": 120, "y": 220},
    ]
    assert brain.requests[1]["context"]["width"] == 800


def test_visual_target_does_not_require_ocr_text():
    image = Image.new("RGB", (800, 600))
    screen = ScreenContext(image, ocr_text=(), uia_metadata=())
    executor = FakeExecutor()
    brain = MockVisualBrain({"goal": [{"action": "click", "x": 100, "y": 200}, {"action": "done", "message": "Playing"}]})
    orchestrator = TaskOrchestrator(
        brain,
        executor,
        lambda: screen,
        verifier=lambda before, after, action, result, state: "success",
    )

    state = orchestrator.run("goal")

    assert state.status == "completed"
    assert executor.calls == [{"action": "click", "target": {"x": 100, "y": 200}}]


def test_ambiguous_screen_waits_for_user_without_more_actions():
    executor = FakeExecutor()
    brain = MockVisualBrain({"goal": [{
        "action": "ask_user",
        "message": "I found Nehru Yadav, Nehru Yadav Family, and Nehru Yadav Official.",
    }]})
    orchestrator = TaskOrchestrator(
        brain,
        executor,
        lambda: ScreenContext(Image.new("RGB", (800, 600)), ocr_text=(
            "Nehru Yadav", "Nehru Yadav Family", "Nehru Yadav Official"
        )),
        verifier=lambda before, after, action, result, state: "success",
    )

    state = orchestrator.run("goal")

    assert state.status == "waiting_for_user"
    assert "Which" not in state.message
    assert executor.calls == []