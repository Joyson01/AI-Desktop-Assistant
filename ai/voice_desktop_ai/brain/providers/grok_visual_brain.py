import base64
from io import BytesIO
import json
import os
from pathlib import Path

from brain.screen_context import BrainInput
from brain.visual_brain import VisualBrainResult


DEFAULT_MODEL = "grok-4.6"
XAI_BASE_URL = "https://api.x.ai/v1"
LOW_CONFIDENCE = 0.7

ACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": [
            "click", "double_click", "right_click", "type", "press",
            "hotkey", "scroll", "wait", "done", "ask_user",
        ]},
        "x": {"type": ["number", "null"]},
        "y": {"type": ["number", "null"]},
        "text": {"type": ["string", "null"]},
        "key": {"type": ["string", "null"]},
        "keys": {"type": ["array", "null"], "items": {"type": "string"}},
        "amount": {"type": ["integer", "null"]},
        "milliseconds": {"type": ["integer", "null"]},
        "message": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "uncertainty": {"type": "string"},
        "rationale": {"type": "string"},
        "expected_state": {
            "type": ["object", "string", "null"],
            "properties": {
                "state": {"type": ["string", "null"]},
                "active_application": {"type": ["string", "null"]},
                "active_window": {"type": ["string", "null"]},
                "url": {"type": ["string", "null"]},
            },
            "additionalProperties": False,
        },
    },
    "required": [
        "action", "x", "y", "text", "key", "keys", "amount",
        "milliseconds", "message", "confidence", "uncertainty", "rationale",
        "expected_state",
    ],
}


SYSTEM_PROMPT = """You are Maruti's visual computer-use decision provider.
The user's goal may be written in English, Hindi (Devanagari), or Hinglish/Roman Hindi.
First interpret the goal's meaning, including Hindi or Hinglish verbs such as kholo,
karo, click karo, search karo, and reload karo, before selecting the visual target.
You MUST visually analyze the screenshot.
You MUST inspect the attached screenshot visually, not rely on OCR alone.
Do not rely only on OCR.
Locate the requested UI element visually and use its visible geometry.
Return ONLY the next action. Return exactly ONE next action, never a sequence and never code or tool calls.
For a visible, uniquely identifiable target, return click with its center x/y.
For a missing, ambiguous, or uncertain target, return ask_user; never invent coordinates.
Coordinates are pixels relative to the supplied screenshot, whose width and height
are included in the user context. Coordinates are relative to screenshot dimensions.
For keyboard requests use press or hotkey.
After this action, an external orchestrator will capture a new screenshot and call you again.
After each action a new screenshot is supplied.
If you can state a reliable expected post-action screen state, include expected_state;
otherwise leave it null. Never claim success from a screenshot merely being available.
For every response, populate rationale with a brief explanation of what you saw
and why the single action or safe question is appropriate.
"""


class GrokVisualBrain:
    """Optional xAI adapter that returns decisions but never executes them."""

    def __init__(self, api_key=None, model=None, transport=None, confidence_threshold=LOW_CONFIDENCE):
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        self.model = model or os.getenv("XAI_MODEL", DEFAULT_MODEL)
        self.confidence_threshold = confidence_threshold
        self.client = transport
        self.last_request = None
        self.last_response_type = None
        if self.client is None and self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key, base_url=XAI_BASE_URL)
            except (ImportError, Exception):
                self.client = None

    @property
    def configured(self):
        return self.client is not None

    def analyze(self, brain_input):
        if not isinstance(brain_input, BrainInput):
            return self._ask_user("Grok requires a BrainInput observation.")
        if not self.configured:
            return self._ask_user("Grok visual brain is not configured.")
        try:
            request = self._build_request(brain_input)
            self.last_request = request
            response = self.client.responses.create(
                model=self.model,
                input=request,
                text={"format": {
                    "type": "json_schema",
                    "name": "maruti_visual_action",
                    "strict": True,
                    "schema": ACTION_SCHEMA,
                }},
                store=False,
            )
            response_text = self._response_text(response)
            self.last_response_type = type(response).__name__
            result = VisualBrainResult.from_payload(json.loads(response_text))
            if result.action.name in {"click", "double_click", "right_click"} and result.confidence < self.confidence_threshold:
                return self._ask_user("I cannot confidently identify the requested screen target.")
            return result
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            return self._ask_user(f"Grok returned an invalid visual decision: {error}")
        except Exception as error:
            return self._ask_user(f"Grok visual analysis failed: {type(error).__name__}.")

    def resolve_website(self, prompt):
        """Return a structured website candidate using the existing Grok client."""
        if not self.configured:
            return None
        response = self.client.responses.create(
            model=self.model,
            input=[{"role": "user", "content": prompt}],
            text={"format": {
                "type": "json_schema",
                "name": "maruti_official_website",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "target": {"type": "string"},
                        "name": {"type": ["string", "null"]},
                        "official_url": {"type": ["string", "null"]},
                        "official_domain": {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                        "reason": {"type": ["string", "null"]},
                    },
                    "required": ["target", "name", "official_url", "official_domain", "confidence", "reason"],
                },
            }},
            store=False,
        )
        return self._response_text(response)

    def _build_request(self, brain_input):
        content = [
            {"type": "input_text", "text": json.dumps({
                "goal": brain_input.goal,
                "screen": brain_input.screen.to_metadata(),
                "action_history": list(brain_input.action_history),
                "last_action": brain_input.last_action,
                "last_verification": brain_input.last_verification,
                "task_step": brain_input.task_step,
                "context": brain_input.context,
            }, ensure_ascii=False)},
            {"type": "input_image", "image_url": _image_data_url(brain_input.screen.screenshot), "detail": "high"},
        ]
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]

    def diagnostics(self, brain_input, result=None):
        """Return request/result metadata safe for logs; never includes image or credentials."""
        request = self.last_request or self._build_request(brain_input)
        image = request[1]["content"][1]
        data = image["image_url"]
        encoded = data.split(",", 1)[1] if "," in data else ""
        return {
            "provider": "xAI",
            "model": self.model,
            "screenshot_width": brain_input.screen.width,
            "screenshot_height": brain_input.screen.height,
            "image_mime_type": data.split(";", 1)[0].removeprefix("data:"),
            "image_byte_length": len(base64.b64decode(encoded)) if encoded else 0,
            "request_contains_image": bool(encoded),
            "response_type": type(result).__name__ if result is not None else self.last_response_type,
            "action_type": result.action.name if result is not None else None,
            "confidence": result.confidence if result is not None else None,
            "expected_state_present": result.expected_state is not None if result is not None else None,
            "rationale_present": bool(result.rationale.strip()) if result is not None else None,
            "validation": "passed" if result is not None else "not_run",
        }

    def debug_request(self, brain_input):
        """Return a redacted request summary for local transport debugging."""
        request = self.last_request or self._build_request(brain_input)
        user_content = request[1]["content"]
        image_url = user_content[1]["image_url"]
        encoded = image_url.split(",", 1)[1] if "," in image_url else ""
        return {
            "endpoint": XAI_BASE_URL + "/responses",
            "model": self.model,
            "message_roles": [message["role"] for message in request],
            "content_types": [item["type"] for item in user_content],
            "image_mime_type": image_url.split(";", 1)[0].removeprefix("data:"),
            "image_byte_length": len(base64.b64decode(encoded)) if encoded else 0,
            "request_contains_image": bool(encoded),
            "prompt_text": SYSTEM_PROMPT,
            "response_format": {
                "type": "json_schema",
                "name": "maruti_visual_action",
                "strict": True,
                "schema": ACTION_SCHEMA,
            },
            "settings": {"store": False},
        }

    @staticmethod
    def _response_text(response):
        if isinstance(response, dict):
            return response["output_text"]
        text = getattr(response, "output_text", None)
        if text:
            return text
        raise ValueError("provider response did not contain output text")

    @staticmethod
    def _ask_user(message):
        return VisualBrainResult.from_payload({
            "action": "ask_user",
            "message": message,
            "confidence": 0.0,
        })


def _image_data_url(image):
    if isinstance(image, bytes):
        encoded = base64.b64encode(image).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    if isinstance(image, (str, Path)):
        path = Path(image)
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        media_type = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        return f"data:{media_type};base64,{encoded}"
    if hasattr(image, "save"):
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    raise TypeError("screenshot must be image bytes, a path, or an image object")
