"""Comprehensive fake-backend integration and lifecycle tests for MARUTI Assistant.

Tests cover:
1. Unified Assistant façade command planning and execution serialization.
2. App launch workflow: 'open Chrome' -> plan/readiness/dry-run.
3. Web search workflow: 'search Python tutorials' -> encoded Google URL.
4. YouTube search & playback workflow: 'search/play Saiyara song' -> OCR verification / manual fallback.
5. Text editing sequence: open notepad -> type hello -> select all -> copy -> paste -> cut -> undo with focus tracking.
6. Hindi / Hinglish voice commands: 'kholo calculator', 'dhoondo scholarship information', 'likho namaste'.
7. Cancellation during execution and declining sensitive confirmation gates.
8. Sensitive click and payment confirmation gates.
9. Credential and secret redaction in action audit logging.
10. Dictation mode activation, literal typing, and graceful deactivation.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from assistant import Assistant
from core.models import (
    ActionPlan,
    ActionRisk,
    AssistantState,
    ExecutionResult,
    VerificationLevel,
)


@pytest.fixture
def dry_assistant():
    return Assistant(dry_run=True, mute=True)


def test_open_chrome_workflow(dry_assistant):
    """Verify 'open Chrome' produces app launch plan and dry-run execution."""
    plan = dry_assistant.plan_command("open Chrome")
    assert plan.intent.name == "open"
    assert plan.intent.args["label"] == "chrome"
    assert plan.risk == ActionRisk.SAFE

    res = dry_assistant.execute_plan(plan)
    assert res.success is True
    assert "Opening chrome" in res.message
    assert res.verification.level == VerificationLevel.PLANNED


def test_search_python_tutorials_workflow(dry_assistant):
    """Verify 'search Python tutorials' encodes query in Google URL."""
    res = dry_assistant.process_text("search Python tutorials")
    assert res.success is True
    assert res.intent_name == "web_search"
    assert "Python tutorials" in res.message

    # Test non-dry-run URL generation
    dry_assistant.context.last_submission_time = 0.0
    with patch.object(dry_assistant.executor.registry.system, "open_url", return_value=(True, "Opening google.com")) as mock_open:
        dry_assistant.dry_run = False
        dry_assistant.process_text("search Python tutorials")
        dry_assistant.dry_run = True
        mock_open.assert_called_once()
        called_url = mock_open.call_args[0][0]
        assert "https://www.google.com/search?q=Python+tutorials" in called_url


def test_youtube_search_and_play_workflow(dry_assistant):
    """Verify YouTube search and playback behavior."""
    # 1. Search YouTube
    res_search = dry_assistant.process_text("search Saiyara song on youtube")
    assert res_search.success is True
    assert "Saiyara song" in res_search.message

    # 2. Play YouTube dry-run
    dry_assistant.context.last_submission_time = 0.0
    res_play = dry_assistant.process_text("play Saiyara song")
    assert res_play.success is True
    assert "Playing Saiyara song on YouTube" in res_play.message

    # 3. Play YouTube non-dry-run when OCR is unavailable: reports manual selection required
    dry_assistant.context.last_submission_time = 0.0
    with patch.object(dry_assistant.executor.registry.perception, "is_ocr_available", return_value=False):
        with patch.object(dry_assistant.executor.registry.browser, "search_youtube", return_value=(True, "Showing results")):
            dry_assistant.dry_run = False
            res_live = dry_assistant.process_text("play Saiyara song")
            dry_assistant.dry_run = True
            assert "Please select a video to play" in res_live.message


def test_notepad_text_editing_ordered_workflow(dry_assistant):
    """Verify ordered editing workflow with focus requirement tracking."""
    # 1. Open Notepad
    plan_open = dry_assistant.plan_command("open notepad")
    assert plan_open.intent.name == "open"
    assert plan_open.target_app == "notepad"

    # 2. Type hello
    plan_type = dry_assistant.plan_command("type hello")
    assert plan_type.intent.name == "type_text"
    assert plan_type.requires_focus is True

    # 3. Select all
    plan_sel = dry_assistant.plan_command("select all")
    assert plan_sel.requires_focus is True

    # 4. Copy
    plan_copy = dry_assistant.plan_command("copy")
    assert plan_copy.intent.name == "clipboard_copy"

    # 5. Paste
    plan_paste = dry_assistant.plan_command("paste")
    assert plan_paste.intent.name == "clipboard_paste"

    # 6. Cut
    plan_cut = dry_assistant.plan_command("cut")
    assert plan_cut.intent.name == "clipboard_cut"

    # 7. Undo
    plan_undo = dry_assistant.plan_command("undo")
    assert plan_undo.intent.name == "edit_undo"


def test_hindi_hinglish_voice_workflows(dry_assistant):
    """Verify Hindi and Hinglish desktop assistant workflows."""
    # 'kholo calculator'
    res_calc = dry_assistant.process_text("kholo calculator")
    assert res_calc.success is True
    assert res_calc.intent_name == "open"

    # 'dhoondo scholarship information'
    res_search = dry_assistant.process_text("dhoondo scholarship information")
    assert res_search.success is True
    assert res_search.intent_name == "web_search"
    assert "scholarship information" in res_search.message

    # 'likho namaste'
    res_type = dry_assistant.process_text("likho namaste")
    assert res_type.success is True
    assert res_type.intent_name == "type_text"


def test_stop_cancel_during_execution(dry_assistant):
    """Verify emergency stop / cancel halts execution immediately."""
    dry_assistant.cancel("User said stop")
    assert dry_assistant.state_machine.is_cancelled is True

    plan = dry_assistant.plan_command("open chrome")
    res = dry_assistant.execute_plan(plan)
    assert res.success is False
    assert "cancelled" in res.message.lower()


def test_declining_sensitive_confirmation_gate():
    """Verify declining a sensitive confirmation prompt safely aborts the action."""
    declining_assistant = Assistant(
        dry_run=True,
        mute=True,
        confirm_callback=lambda prompt: False,  # User says NO
    )

    plan = declining_assistant.plan_command("close the window")
    assert plan.risk == ActionRisk.SENSITIVE

    res = declining_assistant.execute_plan(plan)
    assert res.success is False
    assert "cancelled" in res.message.lower()


def test_approving_sensitive_confirmation_gate():
    """Verify approving a sensitive confirmation prompt allows execution to proceed."""
    approving_assistant = Assistant(
        dry_run=True,
        mute=True,
        confirm_callback=lambda prompt: True,  # User says YES
    )

    plan = approving_assistant.plan_command("close the window")
    assert plan.risk == ActionRisk.SENSITIVE

    res = approving_assistant.execute_plan(plan)
    assert any(phrase in res.message for phrase in ("Window closed", "Closed the window", "Closing", "Okay, I closed it"))


def test_action_log_credential_redaction(dry_assistant, tmp_path):
    """Verify sensitive passwords and OTPs are redacted in the structured JSONL log."""
    from core.action_logger import ActionLogger
    log_file = tmp_path / "test_actions.jsonl"
    dry_assistant.action_logger = ActionLogger(log_path=str(log_file))

    dry_assistant.process_text("type password=SecretPassword999")

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "SecretPassword999" not in content
    assert "[REDACTED" in content


def test_dictation_mode_lifecycle(dry_assistant):
    """Verify explicit start/stop dictation and literal command immunity while active."""
    # 1. Start dictation
    res_start = dry_assistant.process_text("start dictation")
    assert dry_assistant.context.is_dictation_mode is True
    assert "Dictation mode started" in res_start.message

    # 2. Spoken command while in dictation mode must NOT execute as a desktop action
    res_dictated = dry_assistant.process_text("open chrome")
    assert res_dictated.intent_name == "type_text"
    assert dry_assistant.context.is_dictation_mode is True

    # 3. Stop dictation
    res_stop = dry_assistant.process_text("stop dictation")
    assert dry_assistant.context.is_dictation_mode is False
    assert "Dictation mode stopped" in res_stop.message


def test_ask_yes_no_confirmation_tokens(monkeypatch):
    """Verify ask_yes_no accepts confirm, haan, yes and rejects cancel, no, nahi."""
    from main import MarutiApp

    app = MarutiApp(mute=True, dry_run=True, voice_mode=False)

    for affirmative in ("confirm", "yes", "haan", "sure", "ok"):
        monkeypatch.setattr("builtins.input", lambda prompt, a=affirmative: a)
        assert app.ask_yes_no("Proceed?") is True

    for negative in ("cancel", "no", "nahi", "never", ""):
        monkeypatch.setattr("builtins.input", lambda prompt, n=negative: n)
        assert app.ask_yes_no("Proceed?") is False

