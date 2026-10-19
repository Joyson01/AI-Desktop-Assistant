import base64
import json

from PIL import Image

from brain.providers.grok_visual_brain import GrokVisualBrain
from brain.screen_context import BrainInput, ScreenContext
from computer.action_pipeline import ActionPipeline


class FakeResponse:
    def __init__(self, output_text):
        self.output_text = output_text


class FakeTransport:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    class Responses:
        def __init__(self, owner):
            self.owner = owner

        def create(self, **kwargs):
            self.owner.calls.append(kwargs)
            if self.owner.error:
                raise self.owner.error
            return FakeResponse(self.owner.response)

    @property
    def responses(self):
        return self.Responses(self)


def make_input():
    return BrainInput(
        goal="Click the Nehru Yadav account",
        screen=ScreenContext(Image.new("RGB", (800, 600)), active_application="Chrome"),
        action_history=({"action": "wait", "milliseconds": 100},),
        last_action={"action": "click", "x": 20, "y": 30},
        last_verification={"status": "failure"},
        task_step=2,
        context={"current_url": "https://example.test"},
    )


def make_brain(payload):
    transport = FakeTransport(json.dumps(payload))
    return GrokVisualBrain(transport=transport), transport


def test_valid_click_response_returns_one_action():
    brain, transport = make_brain({
        "action": "click", "x": 123, "y": 456, "confidence": 0.94,
        "rationale": "The requested account card is visible.",
        "expected_state": {"state": "account_selected"},
    })

    result = brain.analyze(make_input())

    assert result.action.to_dict() == {"action": "click", "x": 123, "y": 456}
    assert result.confidence == 0.94
    assert result.expected_state == {"state": "account_selected"}
    assert len(transport.calls) == 1


def test_request_contains_goal_context_history_and_image_data_url():
    brain, transport = make_brain({"action": "done", "message": "Complete"})

    brain.analyze(make_input())

    request = transport.calls[0]
    assert request["input"][0]["role"] == "system"
    assert "MUST inspect the attached screenshot visually" in request["input"][0]["content"]
    assert "rationale" in request["input"][0]["content"]
    assert request["model"] == "grok-4.6"
    assert request["store"] is False
    assert request["text"]["format"]["type"] == "json_schema"
    content = request["input"][1]["content"]
    text = json.loads(content[0]["text"])
    assert text["goal"] == "Click the Nehru Yadav account"
    assert text["action_history"] == [{"action": "wait", "milliseconds": 100}]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert base64.b64decode(content[1]["image_url"].split(",", 1)[1])


def test_diagnostics_report_safe_image_metadata_only():
    brain, _ = make_brain({"action": "done", "message": "Complete"})
    brain_input = make_input()
    result = brain.analyze(brain_input)

    diagnostics = brain.diagnostics(brain_input, result)

    assert diagnostics["screenshot_width"] == 800
    assert diagnostics["screenshot_height"] == 600
    assert diagnostics["image_mime_type"] == "image/png"
    assert diagnostics["image_byte_length"] > 0
    assert diagnostics["request_contains_image"] is True
    assert diagnostics["action_type"] == "done"
    assert diagnostics["expected_state_present"] is False
    assert diagnostics["rationale_present"] is False
    assert "api_key" not in diagnostics


def test_invalid_json_and_unsupported_action_become_safe_ask_user_results():
    for response in ("not json", json.dumps({"action": "delete_everything"})):
        transport = FakeTransport(response)
        result = GrokVisualBrain(transport=transport).analyze(make_input())

        assert result.action.name == "ask_user"
        assert len(transport.calls) == 1


def test_low_confidence_click_becomes_ask_user():
    brain, _ = make_brain({"action": "click", "x": 123, "y": 456, "confidence": 0.2})

    result = brain.analyze(make_input())

    assert result.action.name == "ask_user"
    assert result.confidence == 0.0


def test_ambiguous_and_missing_targets_are_returned_without_clicking():
    for message in (
        "Which one: YouTube, YouTube Music, or YouTube Studio?",
        "I cannot find Bluetooth.",
    ):
        brain, _ = make_brain({"action": "ask_user", "message": message, "confidence": 0.0})

        result = brain.analyze(make_input())

        assert result.action.name == "ask_user"
        assert result.action.message == message


def test_done_response_is_supported_without_execution():
    brain, _ = make_brain({"action": "done", "message": "The task is complete."})

    result = brain.analyze(make_input())

    assert result.action.to_dict() == {"action": "done", "message": "The task is complete."}


def test_provider_error_becomes_controlled_ask_user_result():
    transport = FakeTransport(error=TimeoutError("timed out"))

    result = GrokVisualBrain(transport=transport).analyze(make_input())

    assert result.action.name == "ask_user"
    assert "Grok visual analysis failed" in result.action.message


def test_missing_key_is_constructible_without_request(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    brain = GrokVisualBrain()

    assert brain.configured is False
    assert brain.analyze(make_input()).action.name == "ask_user"


def test_brain_has_no_execution_operations():
    brain, _ = make_brain({"action": "click", "x": 10, "y": 20, "confidence": 0.9})

    assert not hasattr(brain, "execute")
    assert not hasattr(brain, "click")


def test_grok_result_reaches_pipeline_fake_executor_only():
    brain, _ = make_brain({"action": "click", "x": 100, "y": 200, "confidence": 0.9})
    calls = []

    class FakeExecutor:
        def execute(self, payload):
            calls.append(payload)
            return {"success": True, "message": "simulated"}

    pipeline = ActionPipeline(brain, FakeExecutor())
    brain_result = brain.analyze(make_input())
    result = pipeline.execute_result(brain_result, make_input().screen.screenshot)

    assert result["success"] is True
    assert calls == [{"action": "click", "target": {"x": 100, "y": 200}}]