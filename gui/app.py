"""PySide6 Graphical User Interface for MARUTI Desktop Assistant.

Provides an interactive desktop interface with:
- Non-blocking QThread workers for speech recognition and command execution.
- Status indicator orb (Listening, Thinking, Executing, Idle).
- Live scrollable transcript of voice/text interactions.
- Command debouncer to suppress duplicate speech recognition returns.
- Interactive text input for silent or hybrid operation.
- Graceful shutdown and worker thread cleanup.
"""
from __future__ import annotations

import logging
import sys
import time
from typing import Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from actions import ActionExecutor
from assistant import Assistant
from brain import Brain
from core.context import ConversationContext
from core.models import AssistantState, ExecutionResult
from intent_router import IntentRouter
from voice.stt import Listener
from voice.tts import Speaker
import config

logger = logging.getLogger("maruti.gui")


class CommandDebouncer:
    """Filters duplicate recognized voice commands received in rapid succession."""

    def __init__(self, window_sec: float = 1.5) -> None:
        self.window_sec = window_sec
        self.last_command: str = ""
        self.last_time: float = 0.0

    def is_duplicate(self, text: str) -> bool:
        now = time.time()
        norm = text.strip().lower()
        if norm == self.last_command and (now - self.last_time < self.window_sec):
            return True
        self.last_command = norm
        self.last_time = now
        return False


class VoiceWorker(QThread):
    """Background worker thread running the continuous audio capture loop."""

    status_signal = Signal(str)
    phrase_signal = Signal(str, float)
    error_signal = Signal(str)

    def __init__(self, listener: Listener, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.listener = listener
        self._running = True

    def stop(self) -> None:
        self._running = False
        if hasattr(self.listener, "cancel"):
            self.listener.cancel()

    def run(self) -> None:
        logger.info("VoiceWorker thread started.")
        self.status_signal.emit("Listening")

        while self._running:
            try:
                # Capture phrase
                phrase, conf = self.listener.listen(timeout=4.0, phrase_time_limit=8.0)
                if phrase and self._running:
                    self.phrase_signal.emit(phrase, conf)
            except Exception as exc:
                if self._running:
                    logger.debug("VoiceWorker loop exception: %s", exc)
                    self.error_signal.emit(str(exc))
            time.sleep(0.05)

        logger.info("VoiceWorker thread stopped.")


class ActionWorker(QThread):
    """Background worker executing desktop actions off the GUI thread."""

    finished_signal = Signal(str, str, bool)  # raw_input, reply, success

    def __init__(
        self,
        executor: Optional[ActionExecutor] = None,
        router: Optional[IntentRouter] = None,
        speaker: Optional[Speaker] = None,
        raw_text: str = "",
        context: Optional[ConversationContext] = None,
        assistant: Optional[Assistant] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.executor = executor
        self.router = router
        self.speaker = speaker
        self.raw_text = raw_text
        self.context = context
        self.assistant = assistant

    def run(self) -> None:
        if self.assistant:
            result = self.assistant.process_text(self.raw_text)
            self.finished_signal.emit(self.raw_text, result.message, result.success)
            return

        # Direct legacy execution fallback
        intent = self.router.route(self.raw_text, context=self.context) if self.router else None
        try:
            if self.executor and intent:
                reply = self.executor.execute(intent)
                success = True
            else:
                reply = "Executor unavailable."
                success = False
        except Exception as exc:
            reply = f"Sorry, that failed: {exc}"
            success = False

        if self.context and intent:
            self.context.update_action(intent.name, reply)

        if self.speaker:
            self.speaker.say(reply)
        self.finished_signal.emit(self.raw_text, reply, success)


class MarutiMainWindow(QMainWindow):
    """Main desktop control window for MARUTI."""

    def __init__(self, dry_run: bool = False, mute: bool = False) -> None:
        super().__init__()
        self.dry_run = dry_run
        self.mute = mute
        self.debouncer = CommandDebouncer(window_sec=1.5)

        # Unified Assistant Facade
        self.assistant = Assistant(
            dry_run=dry_run,
            mute=mute,
            confirm_callback=self._confirm_dialog,
        )
        self.speaker = self.assistant.speaker
        self.listener = self.assistant.listener
        self.context = self.assistant.context
        self.router = self.assistant.router
        self.executor = self.assistant.executor

        # State machine listener
        self.assistant.add_state_listener(self._on_assistant_state_change)

        self.voice_worker: Optional[VoiceWorker] = None
        self._init_ui()

        # Start voice loop if mic is ready
        if self.listener.is_available:
            self.start_listening()
        else:
            self.append_log("System", "Microphone unavailable. You can use standard text input below.")

    def _init_ui(self) -> None:
        self.setWindowTitle("MARUTI — Voice Controlled Desktop Assistant")
        self.setMinimumSize(720, 560)

        # Dark theme stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #12141a;
            }
            QLabel {
                color: #e2e8f0;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
            }
            QCheckBox {
                color: #cbd5e1;
                font-size: 12px;
            }
            QTextEdit {
                background-color: #1a1e28;
                color: #f8fafc;
                border: 1px solid #2d3748;
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                line-height: 1.4;
            }
            QLineEdit {
                background-color: #1e2433;
                color: #ffffff;
                border: 1px solid #3b475e;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #3b82f6;
            }
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton#stopBtn {
                background-color: #dc2626;
            }
            QPushButton#stopBtn:hover {
                background-color: #b91c1c;
            }
            QPushButton#micBtnActive {
                background-color: #ef4444;
            }
        """)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        # Header bar
        header_layout = QHBoxLayout()
        title_label = QLabel("MARUTI Desktop Assistant")
        title_label.setFont(QFont("Ubuntu", 15, QFont.Weight.Bold))

        self.status_badge = QLabel("READY")
        self.status_badge.setStyleSheet("""
            background-color: #059669;
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
            padding: 4px 10px;
            border-radius: 12px;
        """)

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.status_badge)
        main_layout.addLayout(header_layout)

        # Transcript log
        self.transcript_box = QTextEdit()
        self.transcript_box.setReadOnly(True)
        main_layout.addWidget(self.transcript_box, stretch=1)

        # Controls row (Review toggle & Stop button)
        controls_layout = QHBoxLayout()
        self.review_check = QCheckBox("Review voice commands before executing")
        self.review_check.setChecked(config.REVIEW_MODE)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setToolTip("Immediately stop current action, listening, or speech")
        self.stop_btn.clicked.connect(self.handle_stop)

        controls_layout.addWidget(self.review_check)
        controls_layout.addStretch()
        controls_layout.addWidget(self.stop_btn)
        main_layout.addLayout(controls_layout)

        # Bottom Input row
        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a command (e.g. 'open chrome', 'volume 50%', 'scroll down')...")
        self.input_field.returnPressed.connect(self.handle_text_submit)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.handle_text_submit)

        self.mic_btn = QPushButton("Mic: ON")
        self.mic_btn.clicked.connect(self.toggle_mic)

        input_layout.addWidget(self.input_field, stretch=1)
        input_layout.addWidget(self.send_btn)
        input_layout.addWidget(self.mic_btn)
        main_layout.addLayout(input_layout)

        self.append_log("Maruti", "Assistant initialized and ready.")

    def _on_assistant_state_change(
        self,
        old_state: AssistantState,
        new_state: AssistantState,
        message: Optional[str] = None,
    ) -> None:
        """Update GUI status indicator in response to state machine events."""
        state_map = {
            AssistantState.IDLE: ("READY", "#059669"),
            AssistantState.LISTENING: ("LISTENING", "#059669"),
            AssistantState.TRANSCRIBING: ("TRANSCRIBING", "#8b5cf6"),
            AssistantState.REVIEW: ("REVIEW", "#8b5cf6"),
            AssistantState.ROUTING: ("THINKING", "#3b82f6"),
            AssistantState.AWAITING_CONFIRMATION: ("CONFIRMING", "#f59e0b"),
            AssistantState.EXECUTING: ("EXECUTING", "#3b82f6"),
            AssistantState.CANCELLED: ("CANCELLED", "#ef4444"),
            AssistantState.ERROR: ("ERROR", "#dc2626"),
        }
        label, color = state_map.get(new_state, ("BUSY", "#6b7280"))
        self.set_status(label, color)

    def append_log(self, sender: str, message: str) -> None:
        """Append formatted line to the transcript."""
        color = (
            "#60a5fa" if sender == "User"
            else "#34d399" if sender == "Maruti"
            else "#a78bfa" if sender == "Heard"
            else "#f59e0b"
        )
        html = f"<div style='margin-bottom: 6px;'><b style='color: {color};'>[{sender}]:</b> {message}</div>"
        self.transcript_box.append(html)
        self.transcript_box.moveCursor(QTextCursor.MoveOperation.End)

    def set_status(self, text: str, color_hex: str = "#059669") -> None:
        self.status_badge.setText(text.upper())
        self.status_badge.setStyleSheet(f"""
            background-color: {color_hex};
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
            padding: 4px 10px;
            border-radius: 12px;
        """)

    @Slot()
    def handle_stop(self) -> None:
        """Halt speech, execution, and listening immediately."""
        logger.info("Stop button clicked in GUI.")
        self.assistant.cancel("User clicked Stop button")
        self.append_log("System", "Action and voice playback stopped.")
        self.set_status("Stopped", "#ef4444")

    @Slot()
    def handle_text_submit(self) -> None:
        raw_text = self.input_field.text().strip()
        if not raw_text:
            return
        self.input_field.clear()
        self.process_command(raw_text)

    def process_command(self, text: str) -> None:
        """Route and execute command in background worker thread."""
        if self.debouncer.is_duplicate(text):
            logger.info("Suppressed duplicate command: '%s'", text)
            return

        self.context.sync_desktop_state()
        self.append_log("User", text)
        self.set_status("Executing", "#3b82f6")

        # Spawn worker to keep GUI thread responsive
        worker = ActionWorker(
            executor=self.executor,
            router=self.router,
            speaker=self.speaker,
            raw_text=text,
            context=self.context,
            assistant=self.assistant,
            parent=self,
        )
        worker.finished_signal.connect(self.on_action_finished)
        worker.start()

    @Slot(str, str, bool)
    def on_action_finished(self, raw_input: str, reply: str, success: bool) -> None:
        self.append_log("Maruti", reply)
        self.set_status("Listening" if self.voice_worker and self.voice_worker.isRunning() else "Ready", "#059669")

    @Slot(str, float)
    def on_phrase_recognized(self, phrase: str, conf: float) -> None:
        if self.speaker.is_speaking:
            logger.info("Ignored speech recognized in GUI while speaking: '%s'", phrase)
            return

        # Suppress acoustic echo of assistant's own voice
        if self.speaker.last_spoken and (time.time() - self.speaker.last_spoken_time < 2.5):
            p_norm = phrase.lower().strip()
            s_norm = self.speaker.last_spoken.lower().strip()
            if p_norm == s_norm or p_norm in s_norm or s_norm in p_norm:
                logger.info("Suppressed echo in GUI: '%s'", phrase)
                return

        logger.info("Voice recognized in GUI: '%s' (conf=%.2f)", phrase, conf)
        self.append_log("Heard", phrase)

        if self.review_check.isChecked():
            self.input_field.setText(phrase)
            self.input_field.setFocus()
            self.assistant.state_machine.transition_to(AssistantState.REVIEW, message=phrase, force=True)
            self.append_log("System", "Command held for review. Edit above and press Send or Enter to execute.")
            return

        self.process_command(phrase)

    def start_listening(self) -> None:
        if not self.listener.is_available:
            return
        if self.voice_worker is None or not self.voice_worker.isRunning():
            self.voice_worker = VoiceWorker(self.listener, self)
            self.voice_worker.phrase_signal.connect(self.on_phrase_recognized)
            self.voice_worker.start()
            self.mic_btn.setText("Mic: ON")
            self.set_status("Listening", "#059669")

    def stop_listening(self) -> None:
        if self.voice_worker and self.voice_worker.isRunning():
            self.voice_worker.stop()
            self.voice_worker.wait(1000)
            self.voice_worker = None
        self.mic_btn.setText("Mic: OFF")
        self.set_status("Idle", "#6b7280")

    @Slot()
    def toggle_mic(self) -> None:
        if self.voice_worker and self.voice_worker.isRunning():
            self.stop_listening()
        else:
            self.start_listening()

    def _confirm_dialog(self, question: str) -> bool:
        """Prompt confirmation on the main thread safely."""
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "MARUTI Confirmation",
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def closeEvent(self, event) -> None:
        """Clean up background threads on window exit."""
        self.stop_listening()
        self.speaker.say("Goodbye!", block=False)
        event.accept()


def launch_gui(dry_run: bool = False, mute: bool = False) -> None:
    """Entry point for GUI mode."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MarutiMainWindow(dry_run=dry_run, mute=mute)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
