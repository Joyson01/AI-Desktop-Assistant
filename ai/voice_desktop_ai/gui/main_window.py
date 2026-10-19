"""
MARUTI Main Window.
PySide6 GUI for MARUTI AI Voice Controlled Desktop Assistant.
Integrates status orb, transcript bubbles, voice worker, command worker, and safety confirmations.
"""

import sys

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from gui.theme import ModernDarkTheme, ThemeColors
from gui.widgets.status_orb import AssistantState, StatusOrb
from gui.widgets.transcript_view import TranscriptView
from gui.workers import CommandWorker, VoiceWorker


class ConfirmationDialog(QDialog):
    """Modal dialog for critical safety confirmations."""

    def __init__(self, action_name: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Safety Confirmation — MARUTI")
        self.setModal(True)
        self.setFixedSize(420, 180)
        self.setStyleSheet(ModernDarkTheme.get_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title_label = QLabel(f"Confirm Action: {action_name.replace('_', ' ').title()}")
        title_label.setStyleSheet("color: #EF4444; font-size: 14px; font-weight: 700;")
        layout.addWidget(title_label)

        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(f"color: {ThemeColors.TEXT_PRIMARY}; font-size: 13px;")
        layout.addWidget(msg_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.Cancel)
        button_box.button(QDialogButtonBox.StandardButton.Yes).setStyleSheet(
            f"background-color: {ThemeColors.STATE_ERROR}; color: #FFFFFF; font-weight: 600;"
        )
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            f"background-color: {ThemeColors.BG_CARD}; color: {ThemeColors.TEXT_PRIMARY};"
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


class MarutiMainWindow(QMainWindow):
    """
    Main Application Window for MARUTI Desktop Assistant.
    """

    def __init__(self, assistant=None, parent=None):
        super().__init__(parent)
        self.assistant = assistant
        self.setWindowTitle("MARUTI — AI Voice Controlled Desktop Assistant")
        self.resize(780, 820)
        self.setMinimumSize(560, 600)

        # Apply dark theme
        self.setStyleSheet(ModernDarkTheme.get_stylesheet())

        # Setup background workers
        self._init_workers()

        # Build UI layout
        self._init_ui()

        # Connect signals
        self._connect_signals()

        # Greet on startup
        QTimer.singleShot(400, self._startup_greet)

    def _init_workers(self):
        """Initialize voice and command background threads."""
        from assistant import AccessibilityAssistant
        if self.assistant is None:
            self.assistant = AccessibilityAssistant()

        # Command handling worker
        self.command_worker = CommandWorker(self.assistant, parent=self)
        self.command_worker.start()

        # Voice recognition worker
        self.voice_worker = VoiceWorker(self.assistant.speech, parent=self)
        self.voice_worker.start()

    def _init_ui(self):
        """Assemble the complete GUI layout."""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header Frame
        header = self._build_header()
        main_layout.addWidget(header)

        # 2. Quick Action Chips Bar
        quick_chips = self._build_quick_chips()
        main_layout.addWidget(quick_chips)

        # 3. Transcript Area
        self.transcript_view = TranscriptView(self)
        main_layout.addWidget(self.transcript_view, stretch=1)

        # 4. Input Dock Bar
        input_dock = self._build_input_dock()
        main_layout.addWidget(input_dock)

        # 5. Status Bar
        self._build_status_bar()

    def _build_header(self) -> QFrame:
        header = QFrame(self)
        header.setObjectName("HeaderFrame")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(14)

        # Status Orb (Left)
        self.status_orb = StatusOrb(self, size=46)
        layout.addWidget(self.status_orb)

        # Title and Subtitle
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        app_title = QLabel("MARUTI")
        app_title.setObjectName("AppTitle")
        app_subtitle = QLabel("AI Powered Voice Controlled Desktop Assistant")
        app_subtitle.setObjectName("AppSubtitle")
        title_box.addWidget(app_title)
        title_box.addWidget(app_subtitle)
        layout.addLayout(title_box)

        layout.addStretch()

        # Status text indicator badge
        status_box = QVBoxLayout()
        status_box.setAlignment(Qt.AlignmentFlag.AlignRight)
        status_box.setSpacing(2)
        status_header = QLabel("STATUS")
        status_header.setStyleSheet(f"color: {ThemeColors.TEXT_MUTED}; font-size: 10px; font-weight: 700;")
        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("StatusLabel")
        status_box.addWidget(status_header)
        status_box.addWidget(self.status_label)
        layout.addLayout(status_box)

        # Clear transcript button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setToolTip("Clear conversation history")
        self.clear_btn.setFixedHeight(32)
        self.clear_btn.clicked.connect(self._on_clear_transcript)
        layout.addWidget(self.clear_btn)

        return header

    def _build_quick_chips(self) -> QFrame:
        chips_frame = QFrame(self)
        chips_frame.setStyleSheet(f"background-color: {ThemeColors.BG_SURFACE}; border-bottom: 1px solid {ThemeColors.BORDER_COLOR};")
        layout = QHBoxLayout(chips_frame)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(8)

        chips_label = QLabel("Suggestions:")
        chips_label.setStyleSheet(f"color: {ThemeColors.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(chips_label)

        sample_prompts = [
            ("Maruti Hello", "maruti hello"),
            ("YouTube Kholo", "youtube kholo"),
            ("Who is Elon Musk", "who is elon musk"),
            ("Open Calculator", "open calculator"),
            ("What time is it?", "what is the time"),
        ]

        for label, cmd in sample_prompts:
            btn = QPushButton(label)
            btn.setObjectName("QuickChip")
            btn.clicked.connect(lambda checked=False, c=cmd: self._send_command_text(c))
            layout.addWidget(btn)

        layout.addStretch()
        return chips_frame

    def _build_input_dock(self) -> QFrame:
        input_frame = QFrame(self)
        input_frame.setObjectName("InputDock")
        layout = QHBoxLayout(input_frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # Microphone toggle button
        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setObjectName("MicButton")
        self.mic_btn.setToolTip("Toggle Voice Listening (Mic)")
        self.mic_btn.setProperty("listening", "false")
        self.mic_btn.clicked.connect(self._toggle_microphone)
        layout.addWidget(self.mic_btn)

        # Command Text Input
        self.input_edit = QLineEdit(self)
        self.input_edit.setPlaceholderText("Type a voice or text command (e.g. 'maruti hello', 'youtube kholo', 'open chrome')...")
        self.input_edit.returnPressed.connect(self._on_send_clicked)
        layout.addWidget(self.input_edit, stretch=1)

        # Send Button
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("SendButton")
        self.send_btn.clicked.connect(self._on_send_clicked)
        layout.addWidget(self.send_btn)

        return input_frame

    def _build_status_bar(self):
        self.status_bar = QStatusBar(self)
        self.status_bar.setStyleSheet(
            f"background-color: {ThemeColors.BG_SURFACE}; color: {ThemeColors.TEXT_MUTED}; font-size: 11px; border-top: 1px solid {ThemeColors.BORDER_COLOR};"
        )
        self.setStatusBar(self.status_bar)

        # Indicators
        mic_avail = getattr(self.assistant.speech, "is_available", False)
        self.mic_indicator = QLabel(f"🎙 Mic: {'Online' if mic_avail else 'Unavailable (Text Only)'}")
        self.mic_indicator.setStyleSheet(
            f"color: {ThemeColors.STATE_LISTENING if mic_avail else ThemeColors.STATE_ERROR}; margin-right: 12px;"
        )
        self.status_bar.addPermanentWidget(self.mic_indicator)

        provider = getattr(self.assistant.conversation, "provider", None)
        has_gemini = getattr(provider, "client", None) is not None if provider else False
        self.ai_indicator = QLabel(f"⚡ AI: {'Gemini Active' if has_gemini else 'Offline / Rules'}")
        self.ai_indicator.setStyleSheet(
            f"color: {ThemeColors.STATE_THINKING if has_gemini else ThemeColors.TEXT_MUTED}; margin-right: 12px;"
        )
        self.status_bar.addPermanentWidget(self.ai_indicator)

        platform_label = QLabel("🐧 Linux (Wayland/X11)")
        platform_label.setStyleSheet(f"color: {ThemeColors.TEXT_MUTED};")
        self.status_bar.addPermanentWidget(platform_label)

    def _connect_signals(self):
        """Connect worker thread signals to GUI update slots."""
        # Voice worker signals
        self.voice_worker.listening_started.connect(self._on_listening_started)
        self.voice_worker.listening_ended.connect(self._on_listening_ended)
        self.voice_worker.speech_recognized.connect(self._on_speech_recognized)
        self.voice_worker.mic_status_changed.connect(self._on_mic_status_changed)
        self.voice_worker.error_occurred.connect(self._on_error)

        # Command worker signals
        self.command_worker.status_changed.connect(self._on_status_changed)
        self.command_worker.speech_output.connect(self._on_assistant_speech)
        self.command_worker.command_finished.connect(self._on_command_finished)
        self.command_worker.confirmation_requested.connect(self._on_confirmation_requested)
        self.command_worker.error_occurred.connect(self._on_error)

    def _startup_greet(self):
        """Show initial welcome message and instructions."""
        self.transcript_view.add_assistant_message("Hello Boss! Maruti is here. Bataiye, aaj main aapke liye kya kar sakta hoon?")
        mic_avail = getattr(self.assistant.speech, "is_available", False)
        if not mic_avail:
            self.transcript_view.add_system_message("Microphone not detected. Interactive text mode is ready.")

    @Slot()
    def _toggle_microphone(self):
        """Toggle continuous voice listening."""
        if not getattr(self.assistant.speech, "is_available", False):
            self.transcript_view.add_system_message(
                "⚠️ Microphone unavailable: PyAudio or recording device not detected. You can type commands below!"
            )
            return

        currently_listening = self.voice_worker.is_listening
        new_state = not currently_listening
        self.voice_worker.set_listening(new_state)

        self.mic_btn.setProperty("listening", "true" if new_state else "false")
        self.mic_btn.style().unpolish(self.mic_btn)
        self.mic_btn.style().polish(self.mic_btn)

        if new_state:
            self.transcript_view.add_system_message("🎙 Voice listening activated. Speak your command...")
            self.set_status(AssistantState.LISTENING)
        else:
            self.transcript_view.add_system_message("Voice listening paused.")
            self.set_status(AssistantState.IDLE)

    @Slot()
    def _on_send_clicked(self):
        """Handle send button click or Enter key in input box."""
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()
        self._send_command_text(text)

    def _send_command_text(self, text: str):
        """Send a command text to the assistant worker."""
        self.transcript_view.add_user_message(text)
        self.set_status(AssistantState.THINKING)
        self.command_worker.post_command(text, direct=True)

    # --- Worker Slots ---

    @Slot()
    def _on_listening_started(self):
        self.set_status(AssistantState.LISTENING)

    @Slot()
    def _on_listening_ended(self):
        if not self.voice_worker.is_listening:
            self.set_status(AssistantState.IDLE)

    @Slot(str)
    def _on_speech_recognized(self, text: str):
        if text:
            self.transcript_view.add_user_message(f"🎙 {text}")
            self.set_status(AssistantState.THINKING)
            self.command_worker.post_command(text, direct=False)

    @Slot(str)
    def _on_assistant_speech(self, message: str):
        self.transcript_view.add_assistant_message(message)
        self.set_status(AssistantState.SPEAKING)

    @Slot(str)
    def _on_status_changed(self, status: str):
        self.set_status(status)

    @Slot(bool)
    def _on_command_finished(self, success: bool):
        if self.voice_worker.is_listening:
            self.set_status(AssistantState.LISTENING)
        else:
            self.set_status(AssistantState.IDLE)

    @Slot(str, str)
    def _on_confirmation_requested(self, action_type: str, prompt_message: str):
        dialog = ConfirmationDialog(action_type, prompt_message, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.transcript_view.add_user_message("Yes")
            self.command_worker.post_command("yes")
        else:
            self.transcript_view.add_user_message("Cancel")
            self.command_worker.post_command("cancel")

    @Slot(bool)
    def _on_mic_status_changed(self, available: bool):
        self.mic_indicator.setText(f"🎙 Mic: {'Online' if available else 'Unavailable (Text Only)'}")
        self.mic_indicator.setStyleSheet(
            f"color: {ThemeColors.STATE_LISTENING if available else ThemeColors.STATE_ERROR}; margin-right: 12px;"
        )

    @Slot(str)
    def _on_error(self, message: str):
        self.set_status(AssistantState.ERROR)
        self.transcript_view.add_system_message(f"⚠️ {message}")

    @Slot()
    def _on_clear_transcript(self):
        self.transcript_view.clear()
        self.transcript_view.add_system_message("Transcript cleared.")

    def set_status(self, state: AssistantState | str):
        """Update orb state and status text badge."""
        self.status_orb.set_state(state)
        state_str = state.value if isinstance(state, AssistantState) else str(state)
        self.status_label.setText(state_str)

    def closeEvent(self, event):
        """Ensure background threads are safely terminated on window close."""
        self.voice_worker.stop()
        self.command_worker.stop()
        event.accept()
