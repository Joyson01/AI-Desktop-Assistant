"""
Unit and integration tests for MARUTI PySide6 GUI.
Tests run headless using QT_QPA_PLATFORM=offscreen.
"""

import os
import sys
import time
import pytest

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from assistant import AccessibilityAssistant
from gui.main_window import ConfirmationDialog, MarutiMainWindow
from gui.theme import ModernDarkTheme, ThemeColors
from gui.widgets.status_orb import AssistantState, StatusOrb
from gui.widgets.transcript_view import TranscriptView
from gui.workers import CommandWorker, VoiceWorker


@pytest.fixture(scope="session")
def qapp():
    """Ensure a single persistent QApplication instance exists with offscreen platform."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def mock_assistant(monkeypatch):
    """Create a lightweight dry-run AccessibilityAssistant with mocked network/speech."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setenv("VOICE_ASSISTANT_DRY_RUN", "1")

    assistant = AccessibilityAssistant(dry_run=True)
    assistant.speech.is_available = False
    assistant.observe = lambda *args, **kwargs: None
    return assistant


def test_theme_and_colors():
    """Verify theme constants and stylesheet generation."""
    stylesheet = ModernDarkTheme.get_stylesheet()
    assert ThemeColors.BG_DARK in stylesheet
    assert ThemeColors.ACCENT in stylesheet
    assert ThemeColors.STATE_LISTENING in stylesheet


def test_status_orb_states(qapp):
    """Verify StatusOrb states and paint event."""
    orb = StatusOrb(size=40)
    for state in AssistantState:
        orb.set_state(state)
        assert orb.state == state
    orb.repaint()


def test_transcript_view(qapp):
    """Verify transcript adds user, assistant, and system bubbles cleanly."""
    transcript = TranscriptView()
    transcript.add_user_message("Hello from user")
    transcript.add_assistant_message("Hello from Maruti")
    transcript.add_system_message("System alert")

    # Ensure layout items were added
    assert transcript._layout.count() >= 4  # 3 messages + stretch
    transcript.clear()
    assert transcript._layout.count() == 1  # Only stretch remains


def test_gui_startup_without_api_key(qapp, mock_assistant):
    """Verify MarutiMainWindow starts and renders without API keys."""
    window = MarutiMainWindow(assistant=mock_assistant)
    assert window.windowTitle() == "MARUTI — AI Voice Controlled Desktop Assistant"
    assert window.status_orb.state == AssistantState.IDLE
    assert "Unavailable" in window.mic_indicator.text() or "Offline" in window.ai_indicator.text()
    window.close()


def test_gui_mic_toggle_graceful_when_unavailable(qapp, mock_assistant):
    """Verify clicking mic button when mic is unavailable shows non-fatal warning."""
    window = MarutiMainWindow(assistant=mock_assistant)
    # Microphone is unavailable in mock_assistant
    window._toggle_microphone()
    assert window.voice_worker.is_listening is False
    window.close()


def test_command_worker_execution(qapp, mock_assistant):
    """Verify CommandWorker handles text command and emits signals."""
    worker = CommandWorker(mock_assistant)
    started_signals = []
    finished_signals = []
    speech_signals = []

    worker.command_started.connect(started_signals.append)
    worker.command_finished.connect(finished_signals.append)
    worker.speech_output.connect(speech_signals.append)

    worker.start()
    worker.post_command("maruti hello", direct=True)

    # Wait briefly for worker queue processing
    for _ in range(50):
        qapp.processEvents()
        if finished_signals:
            break
        time.sleep(0.05)

    worker.stop()

    assert "maruti hello" in started_signals
    assert len(finished_signals) > 0
    assert any("Hello" in s or "help" in s.lower() for s in speech_signals)


def test_command_worker_safety_confirmation(qapp, mock_assistant):
    """Verify dangerous command (shutdown) triggers safety confirmation signal."""
    worker = CommandWorker(mock_assistant)
    confirm_signals = []
    worker.confirmation_requested.connect(lambda action, prompt: confirm_signals.append((action, prompt)))

    worker.start()
    worker.post_command("shutdown", direct=True)

    for _ in range(50):
        qapp.processEvents()
        if confirm_signals:
            break
        time.sleep(0.05)

    worker.stop()

    assert len(confirm_signals) == 1
    assert confirm_signals[0][0] == "shutdown"
    assert "shut down" in confirm_signals[0][1].lower()


def test_command_worker_error_recovery(qapp, mock_assistant):
    """Verify exceptions inside assistant handler emit error_occurred without crashing worker."""
    def broken_handle(*args, **kwargs):
        raise RuntimeError("Simulated internal failure")

    mock_assistant.handle = broken_handle
    worker = CommandWorker(mock_assistant)
    errors = []
    finished = []
    worker.error_occurred.connect(errors.append)
    worker.command_finished.connect(finished.append)

    worker.start()
    worker.post_command("crash test", direct=True)

    for _ in range(50):
        qapp.processEvents()
        if finished:
            break
        time.sleep(0.05)

    worker.stop()

    assert len(errors) == 1
    assert "Simulated internal failure" in errors[0]
    assert finished == [False]


def test_confirmation_dialog_rendering(qapp):
    """Verify ConfirmationDialog modal renders cleanly."""
    dialog = ConfirmationDialog("shutdown", "Are you sure you want to shut down the computer?")
    assert "shutdown" in dialog.windowTitle().lower() or "safety" in dialog.windowTitle().lower()
    dialog.reject()

