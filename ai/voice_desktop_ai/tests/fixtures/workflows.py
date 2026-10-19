from brain.screen_context import BrainInput
from brain.visual_brain import MockVisualBrain, VisualBrainResult
from verification.verifier import VerificationResult


class WorkflowBrain(MockVisualBrain):
    """A MockVisualBrain that chooses its next result from the observed state."""

    def __init__(self, responses_by_state):
        super().__init__({"fixture": {"action": "done", "message": "unused"}})
        self.responses_by_state = {
            state: list(responses) for state, responses in responses_by_state.items()
        }

    def analyze(self, brain_input):
        if not isinstance(brain_input, BrainInput):
            raise TypeError("WorkflowBrain requires BrainInput")
        self.inputs.append(brain_input)
        self.last_request = {
            "goal": brain_input.goal,
            "screenshot": brain_input.screen.screenshot,
            "context": brain_input.context | brain_input.screen.to_metadata(),
            "history": list(brain_input.action_history),
        }
        responses = self.responses_by_state.get(brain_input.screen.state, [])
        payload = responses.pop(0) if responses else {
            "action": "ask_user",
            "message": f"No simulated decision for screen {brain_input.screen.state}.",
        }
        return VisualBrainResult.from_payload(payload)


class WorkflowVerifier:
    def __init__(self, expected_states):
        self.expected_states = list(expected_states)
        self.calls = []

    def __call__(self, before, after, action, result, state):
        expected = self.expected_states.pop(0) if self.expected_states else None
        observed = after.state
        self.calls.append({"before": before.state, "after": observed, "expected": expected})
        if expected is None:
            return VerificationResult("uncertain", 0.0, "No simulated expectation.", None, observed)
        if observed == expected:
            return VerificationResult("success", 1.0, "Simulated transition matched.", expected, observed)
        return VerificationResult("failure", 1.0, "Simulated transition did not match.", expected, observed)