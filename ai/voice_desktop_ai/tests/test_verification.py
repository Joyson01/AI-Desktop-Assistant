from PIL import Image

from brain.screen_context import ScreenContext
from brain.task_orchestrator import TaskOrchestrator
from brain.visual_brain import MockVisualBrain
from verification.verifier import RuleBasedVerifier, VerificationResult


class FakeExecutor:
    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    def execute(self, payload):
        self.calls.append(payload)
        return self.results.pop(0) if self.results else {"success": True, "message": "executed"}


def screen(state, ocr_text=()):
    return ScreenContext(Image.new("RGB", (800, 600)), state=state, ocr_text=ocr_text)


def test_rule_verifier_detects_chrome_youtube_search_and_play_states():
    verifier = RuleBasedVerifier()
    transitions = [
        ("desktop", "chrome_open", "chrome_open"),
        ("chrome_open", "youtube_open", "youtube_open"),
        ("youtube_open", "search_results", "search_results"),
        ("search_results", "playing", "playing"),
    ]

    for before_state, after_state, expected in transitions:
        result = verifier.verify(screen(before_state), screen(after_state), expected)
        assert result.status == "success"
        assert result.expected_state == expected
        assert result.observed_state["state"] == after_state


def test_rule_verifier_reports_wrong_screen_as_failure():
    result = RuleBasedVerifier().verify(screen("desktop"), screen("settings"), "chrome_open")

    assert result == VerificationResult(
        "failure", 1.0, "Expected screen state was not observed.", "chrome_open", {"state": "settings"}
    )


def test_rule_verifier_reports_missing_expectation_as_uncertain():
    result = RuleBasedVerifier().verify(screen("youtube_open"), screen("playing"), None)

    assert result.status == "uncertain"
    assert not result.success


def test_verification_does_not_require_ocr():
    result = RuleBasedVerifier().verify(screen("search_results", ocr_text=()), screen("playing"), "playing")

    assert result.success is True


def test_rule_verifier_only_reports_data_without_computer_control():
    verifier = RuleBasedVerifier({"click": "chrome_open"})

    assert not hasattr(verifier, "click")
    assert not hasattr(verifier, "execute")


def test_fresh_screenshot_without_expected_state_is_not_success():
    before = screen("desktop")
    after = screen("desktop")
    result = RuleBasedVerifier().verify(before, after, None)

    assert result.status == "uncertain"
    assert result.success is False


def test_expected_state_is_carried_by_visual_result():
    result = MockVisualBrain({"goal": [{
        "action": "click", "x": 100, "y": 100,
        "expected_state": "chrome_open",
    }]}).analyze("goal", object())

    assert result.expected_state == "chrome_open"
    assert result.to_payload()["expected_state"] == "chrome_open"


def test_orchestrator_passes_structured_verification_to_next_brain_input():
    executor = FakeExecutor()
    brain = MockVisualBrain({"goal": [
        {"action": "click", "x": 100, "y": 200},
        {"action": "done", "message": "Chrome opened"},
    ]})
    observed = iter([screen("desktop"), screen("chrome_open"), screen("chrome_open")])
    verification = VerificationResult(
        "success", 0.95, "Chrome became active.", "chrome_open", {"state": "chrome_open"}
    )
    orchestrator = TaskOrchestrator(
        brain,
        executor,
        lambda: next(observed),
        verifier=lambda before, after, action, result, state: verification,
    )

    state = orchestrator.run("goal")

    assert state.status == "completed"
    assert brain.inputs[1].last_verification == verification.to_dict()
    assert state.action_history[0]["result"]["verification_result"] == verification.to_dict()


def test_verification_failure_reanalyzes_and_retry_can_succeed():
    executor = FakeExecutor()
    brain = MockVisualBrain({"goal": [
        {"action": "click", "x": 100, "y": 200},
        {"action": "click", "x": 120, "y": 220},
        {"action": "done", "message": "Recovered"},
    ]})
    observed = iter([screen("desktop"), screen("desktop"), screen("chrome_open"), screen("chrome_open")])
    outcomes = iter([VerificationResult("failure", 1.0, "Chrome did not open."), VerificationResult("success", 1.0, "Chrome opened.")])
    orchestrator = TaskOrchestrator(
        brain,
        executor,
        lambda: next(observed),
        verifier=lambda before, after, action, result, state: next(outcomes),
        max_retries=1,
    )

    state = orchestrator.run("goal")

    assert state.status == "completed"
    assert len(executor.calls) == 2