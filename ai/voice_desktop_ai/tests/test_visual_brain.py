from PIL import Image
import pytest

from brain.visual_brain import MockVisualBrain, VisualBrain, VisualBrainResult
from computer.actions import Action


def test_mock_visual_brain_implements_interface_and_receives_screen_context():
    brain = MockVisualBrain()
    screenshot = Image.new("RGB", (20, 10))
    context = {"active_application": "Chrome", "screen_width": 20}
    history = [{"action": "wait", "milliseconds": 100}]

    result = brain.analyze("click test", screenshot, context, history)

    assert isinstance(brain, VisualBrain)
    assert result.action == Action.from_dict({"action": "click", "x": 100, "y": 200})
    assert brain.last_request == {
        "goal": "click test",
        "screenshot": screenshot,
        "context": context,
        "history": history,
    }


def test_mock_visual_brain_returns_type_action():
    result = MockVisualBrain().analyze("typing test", object())

    assert result.action.to_dict() == {"action": "type", "text": "hello"}


def test_ambiguous_target_returns_ask_user_without_clicking():
    result = MockVisualBrain().analyze("ambiguous target", object())

    assert result.action.name == "ask_user"
    assert result.confidence == 0.2
    assert result.uncertainty == "multiple matching targets"


def test_done_result_is_supported():
    result = VisualBrainResult.from_payload({"action": "done", "message": "Finished"})

    assert result.action.to_dict() == {"action": "done", "message": "Finished"}


def test_invalid_brain_result_is_rejected():
    with pytest.raises(ValueError):
        VisualBrainResult.from_payload({"action": "run_python", "code": "print(1)"})

    with pytest.raises(ValueError):
        VisualBrainResult.from_payload({"action": "click", "x": 10, "y": 10, "confidence": 2})


def test_visual_brain_only_produces_data_and_does_not_execute_actions():
    brain = MockVisualBrain()

    result = brain.analyze("click test", object())

    assert isinstance(result, VisualBrainResult)
    assert not hasattr(brain, "execute")
    assert not hasattr(brain, "click")