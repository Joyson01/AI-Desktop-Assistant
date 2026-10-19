from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationResult:
	status: str
	confidence: float = 0.0
	message: str = ""
	expected_state: object = None
	observed_state: object = None

	@property
	def success(self):
		return self.status == "success"

	def to_dict(self):
		return {
			"status": self.status,
			"confidence": self.confidence,
			"message": self.message,
			"expected_state": self.expected_state,
			"observed_state": self.observed_state,
		}



class RuleBasedVerifier:
	def __init__(self, action_states=None):
		self.action_states = dict(action_states or {})

	def verify(self, before, after, expected_state=None):
		observed_state = {"state": getattr(after, "state", "")}
		if expected_state is None:
			return VerificationResult("uncertain", 0.0, "No expected screen state was provided.", None, observed_state)
		if isinstance(expected_state, dict):
			matches = True
			for key, val in expected_state.items():
				after_val = getattr(after, key, None)
				if after_val is None and isinstance(after, dict):
					after_val = after.get(key)
				if after_val != val:
					matches = False
					break
			if matches:
				return VerificationResult("success", 1.0, "Expected screen state was observed.", expected_state, observed_state)
			return VerificationResult("failure", 1.0, "Expected screen state was not observed.", expected_state, observed_state)
		if observed_state["state"] == expected_state:
			return VerificationResult("success", 1.0, "Expected screen state was observed.", expected_state, observed_state)
		return VerificationResult("failure", 1.0, "Expected screen state was not observed.", expected_state, observed_state)


def state_valid(state):
	return state is not None and hasattr(state, "ui_elements")


def verify_action(refresh, before=None):
	return state_valid(refresh())
