import assistant
from brain.screen_context import ScreenContext
from PIL import Image


class FakeConfig:
    api_key = "test-key"
    model = "grok-test"
    configured = True


def test_grok_live_mode_is_off_by_default(monkeypatch):
    monkeypatch.delenv("MARUTI_GROK_LIVE", raising=False)
    monkeypatch.setattr(assistant, "load_provider_config", lambda: FakeConfig())

    instance = assistant.AccessibilityAssistant(dry_run=True)

    assert instance.grok_live is False
    assert instance.grok_orchestrator is None


def test_enabled_grok_route_handles_unknown_multi_step_goal(monkeypatch):
    monkeypatch.setenv("MARUTI_GROK_LIVE", "1")
    monkeypatch.setattr(assistant, "load_provider_config", lambda: FakeConfig())
    handled = []
    monkeypatch.setattr(assistant.AccessibilityAssistant, "_handle_grok", lambda self, goal: handled.append(goal) or True)
    instance = assistant.AccessibilityAssistant(dry_run=True)

    assert instance.handle("open Chrome and search YouTube") is True
    assert handled == ["open Chrome and search YouTube"]


def test_grok_failure_falls_back_without_speaking_provider_error(monkeypatch):
    monkeypatch.setenv("MARUTI_GROK_LIVE", "1")
    monkeypatch.setattr(assistant, "load_provider_config", lambda: FakeConfig())
    spoken = []
    monkeypatch.setattr(assistant, "speak", spoken.append)
    instance = assistant.AccessibilityAssistant(dry_run=True)
    instance.grok_orchestrator = type("FailingOrchestrator", (), {
        "run": lambda self, goal: type("State", (), {"status": "waiting_for_user", "message": "Grok visual analysis failed: TimeoutError."})()
    })()

    assert instance._handle_grok("open Chrome") is None
    assert spoken == []


def test_grok_transition_requires_semantic_expected_state():
    before = ScreenContext(Image.new("RGB", (800, 600)), state="desktop")
    after = ScreenContext(Image.new("RGB", (800, 600)), state="chrome_open")
    state = type("TaskState", (), {"expected_state": None})()

    result = assistant.AccessibilityAssistant._verify_grok_transition(
        before, after, {"action": "click"}, {"success": True}, state
    )

    assert result.status == "uncertain"
    assert result.success is False


def test_grok_transition_uses_expected_state_evidence():
    before = ScreenContext(Image.new("RGB", (800, 600)), state="desktop")
    after = ScreenContext(Image.new("RGB", (800, 600)), state="chrome_open")
    state = type("TaskState", (), {"expected_state": "chrome_open"})()

    result = assistant.AccessibilityAssistant._verify_grok_transition(
        before, after, {"action": "click"}, {"success": True}, state
    )

    assert result.status == "success"
    assert result.expected_state == "chrome_open"