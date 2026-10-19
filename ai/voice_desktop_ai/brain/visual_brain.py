from dataclasses import dataclass
import math
from typing import Protocol, runtime_checkable

from computer.actions import Action, ActionValidator
from brain.screen_context import BrainInput


@runtime_checkable
class VisualBrain(Protocol):
    def analyze(self, brain_input, screenshot=None, context=None, history=None):
        """Return a visual decision without executing computer actions."""


@dataclass(frozen=True)
class VisualBrainResult:
    action: Action
    confidence: float = 1.0
    uncertainty: str = ""
    rationale: str = ""
    expected_state: object = None

    @classmethod
    def from_payload(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("visual brain result must be an object")
        action_payload = payload.get("action")
        if isinstance(action_payload, str):
            action_payload = {key: value for key, value in payload.items() if key != "confidence"}
        valid, message = ActionValidator.validate(action_payload)
        if not valid:
            raise ValueError(message)
        confidence = payload.get("confidence", 1.0)
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("confidence must be a finite number between 0 and 1")
        return cls(
            action=Action.from_dict(action_payload),
            confidence=float(confidence),
            uncertainty=str(payload.get("uncertainty", "")),
            rationale=str(payload.get("rationale", "")),
            expected_state=payload.get("expected_state"),
        )

    def to_payload(self):
        payload = self.action.to_dict()
        payload["confidence"] = self.confidence
        if self.uncertainty:
            payload["uncertainty"] = self.uncertainty
        if self.rationale:
            payload["rationale"] = self.rationale
        if self.expected_state is not None:
            payload["expected_state"] = self.expected_state
        return payload


class MockVisualBrain:
    def __init__(self, responses=None):
        defaults = {
            "click test": {"action": "click", "x": 100, "y": 200},
            "typing test": {"action": "type", "text": "hello"},
            "ambiguous target": {
                "action": "ask_user",
                "message": "I found two similar targets. Which one should I select?",
                "confidence": 0.2,
                "uncertainty": "multiple matching targets",
            },
        }
        self.responses = responses or defaults
        self.responses = {
            goal: list(payload) if isinstance(payload, list) else payload
            for goal, payload in self.responses.items()
        }
        self.last_request = None
        self.requests = []
        self.inputs = []

    def analyze(self, goal_or_input, screenshot=None, context=None, history=None):
        if isinstance(goal_or_input, BrainInput):
            self.inputs.append(goal_or_input)
            goal = goal_or_input.goal
            screenshot = goal_or_input.screen.screenshot
            context = goal_or_input.context | goal_or_input.screen.to_metadata()
            history = list(goal_or_input.action_history)
        else:
            goal = goal_or_input
        self.last_request = {
            "goal": goal,
            "screenshot": screenshot,
            "context": context,
            "history": history,
        }
        self.requests.append(self.last_request)
        payload = self.responses.get(str(goal).strip().lower())
        if isinstance(payload, list):
            payload = payload.pop(0) if payload else None
        if payload is None:
            payload = {
                "action": "ask_user",
                "message": "I do not have a deterministic mock decision for that goal.",
                "confidence": 0.0,
            }
        return VisualBrainResult.from_payload(payload)