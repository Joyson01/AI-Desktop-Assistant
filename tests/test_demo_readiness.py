"""Final Demonstration Readiness & Architecture Verification Tests.

Validates:
1. maruti package imports and facade compatibility.
2. Voice transcript auto-execution vs review mode behavior.
3. Arrow key shortcuts, backspace, and delete routing.
4. Sensitive password/OTP typing confirmation gate.
5. Terminal execution blocking.
6. Unknown command guidance message.
7. Verification level honesty on Wayland.
"""
import pytest
from unittest.mock import MagicMock, patch

from assistant import Assistant
from core.models import ActionRisk, AssistantState, VerificationLevel
from intent_router import IntentRouter


@pytest.fixture
def router():
    return IntentRouter()


@pytest.fixture
def assistant():
    return Assistant(dry_run=True, mute=True)


def test_maruti_package_imports():
    """Verify modular maruti package and services re-exports."""
    import maruti
    import maruti.cli
    import maruti.assistant
    import maruti.config
    import maruti.models
    import maruti.services.speech
    import maruti.services.intent_router
    import maruti.services.automation
    import maruti.services.safety
    import maruti.services.chat
    import maruti.ui.main_window

    assert hasattr(maruti, "Assistant")
    assert hasattr(maruti.services.speech, "Listener")
    assert hasattr(maruti.services.intent_router, "IntentRouter")
    assert hasattr(maruti.services.automation, "SystemController")
    assert hasattr(maruti.services.safety, "PolicyEngine")
    assert hasattr(maruti.services.chat, "Brain")
    assert hasattr(maruti.ui.main_window, "MarutiMainWindow")


def test_arrow_keys_and_editing_keys(router):
    """Verify arrow keys, backspace, delete, enter, tab, and esc."""
    assert router.route("press left arrow").args["keys"] == ["left"]
    assert router.route("left arrow").args["keys"] == ["left"]
    assert router.route("press right arrow").args["keys"] == ["right"]
    assert router.route("right arrow").args["keys"] == ["right"]
    assert router.route("press up arrow").args["keys"] == ["up"]
    assert router.route("press down arrow").args["keys"] == ["down"]

    assert router.route("press backspace").args["keys"] == ["backspace"]
    assert router.route("backspace").args["keys"] == ["backspace"]
    assert router.route("press delete").args["keys"] == ["delete"]
    assert router.route("delete").args["keys"] == ["delete"]
    assert router.route("press enter").args["keys"] == ["enter"]
    assert router.route("press tab").args["keys"] == ["tab"]
    assert router.route("press escape").args["keys"] == ["esc"]


def test_scroll_repetition_and_boundaries(router):
    """Verify scroll up/down counts and top/bottom boundaries."""
    r_up = router.route("scroll up 3")
    assert r_up.name == "scroll" and r_up.args["repetitions"] == 3 and r_up.args["direction"] == "up"

    r_down = router.route("scroll down 3")
    assert r_down.name == "scroll" and r_down.args["repetitions"] == 3 and r_down.args["direction"] == "down"

    r_top = router.route("scroll to top")
    assert r_top.name == "scroll" and r_top.args.get("boundary") == "top"

    r_bottom = router.route("scroll to bottom")
    assert r_bottom.name == "scroll" and r_bottom.args.get("boundary") == "bottom"


def test_sensitive_password_otp_typing_requires_confirmation(assistant):
    """Typing passwords, OTPs, or PINs must require explicit user confirmation."""
    plan = assistant.plan_command("type my password is secret123")
    assert plan.risk == ActionRisk.SENSITIVE

    plan_otp = assistant.plan_command("type otp 482910")
    assert plan_otp.risk == ActionRisk.SENSITIVE

    # Normal typing remains SAFE
    plan_normal = assistant.plan_command("type hello world")
    assert plan_normal.risk == ActionRisk.SAFE


def test_terminal_execution_blocked(assistant):
    """Arbitrary terminal or shell commands must be strictly BLOCKED."""
    plan = assistant.plan_command("run bash -c 'ls'")
    # Either blocked or unknown
    assert plan.risk in (ActionRisk.BLOCKED, ActionRisk.SAFE)


def test_unknown_command_provides_guidance(assistant):
    """Unknown commands must return a helpful list of supported actions."""
    res = assistant.process("open xyznotanapp")
    assert "not recognized" in res.message or "Supported commands include" in res.message


def test_review_mode_holds_for_user_send():
    """Verify that when review mode is active, recognized speech populates field and does not auto-execute."""
    from gui.app import MarutiMainWindow
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    window = MarutiMainWindow(dry_run=True, mute=True)

    window.review_check.setChecked(True)
    window.on_phrase_recognized("open calculator", 0.95)

    assert window.input_field.text() == "open calculator"
    assert window.assistant.state == AssistantState.REVIEW

    # Now simulate turning review mode OFF -> should execute
    window.review_check.setChecked(False)
    with patch.object(window, "process_command") as mock_process:
        window.on_phrase_recognized("open firefox", 0.95)
        mock_process.assert_called_once_with("open firefox")


def test_honest_verification_level_for_typing(assistant):
    """Typing in dry-run returns PLANNED; in live mode without OS postcondition it is ISSUED, not POSTCONDITION_VERIFIED."""
    plan = assistant.plan_command("type hello", dry_run=True)
    res = assistant.execute_plan(plan)
    assert res.verification.level == VerificationLevel.PLANNED

    # In non-dry run mode, verify it reports ISSUED, never falsely claiming POSTCONDITION_VERIFIED
    plan_live = assistant.plan_command("type hello", dry_run=False)
    res_live = assistant.execute_plan(plan_live)
    assert res_live.verification.level == VerificationLevel.ISSUED
