import json

from PIL import Image

from brain.providers.grok_visual_brain import GrokVisualBrain
from brain.screen_context import BrainInput, ScreenContext


def test_debug_request_redacts_image_data_and_exposes_safe_contract():
    brain = GrokVisualBrain(transport=object())
    image = Image.new("RGB", (320, 240), "white")
    brain_input = BrainInput("click the visible button", ScreenContext(image))

    debug = brain.debug_request(brain_input)
    serialized = json.dumps(debug)

    assert debug["endpoint"] == "https://api.x.ai/v1/responses"
    assert debug["message_roles"] == ["system", "user"]
    assert debug["content_types"] == ["input_text", "input_image"]
    assert debug["image_mime_type"] == "image/png"
    assert debug["image_byte_length"] > 0
    assert debug["request_contains_image"] is True
    assert debug["response_format"]["type"] == "json_schema"
    assert debug["response_format"]["strict"] is True
    assert "base64" not in serialized
    assert "data:image" not in serialized
    assert "api_key" not in serialized


def test_debug_request_does_not_call_transport():
    class UnexpectedTransport:
        def __getattr__(self, name):
            raise AssertionError(f"unexpected transport access: {name}")

    brain = GrokVisualBrain(transport=UnexpectedTransport())
    brain_input = BrainInput("reload the page", ScreenContext(Image.new("RGB", (10, 10))))

    debug = brain.debug_request(brain_input)

    assert debug["model"] == "grok-4.6"