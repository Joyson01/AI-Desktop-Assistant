"""
MARUTI Worker Threads.
Provides QThread-based asynchronous workers for speech recognition and command execution
so the Qt GUI event loop is never blocked.
"""

from queue import Empty, Queue
import time

from PySide6.QtCore import QObject, QThread, Signal

from gui.widgets.status_orb import AssistantState
import tts


class VoiceWorker(QThread):
    """
    Background worker thread for microphone listening and STT.
    Avoids blocking the UI when waiting for speech audio or calling Google STT.
    """
    listening_started = Signal()
    listening_ended = Signal()
    speech_recognized = Signal(str)
    mic_status_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, speech_service, parent=None):
        super().__init__(parent)
        self.speech_service = speech_service
        self._is_running = True
        self._listen_enabled = False

    @property
    def is_listening(self) -> bool:
        return self._listen_enabled

    def set_listening(self, enabled: bool):
        self._listen_enabled = enabled

    def stop(self):
        self._is_running = False
        self._listen_enabled = False
        self.wait(1500)

    def run(self):
        while self._is_running:
            if not self._listen_enabled:
                self.msleep(100)
                continue

            # Verify microphone availability
            if not getattr(self.speech_service, "is_available", False):
                self.mic_status_changed.emit(False)
                self.error_occurred.emit("Microphone not available or disconnected.")
                self._listen_enabled = False
                self.msleep(500)
                continue

            self.mic_status_changed.emit(True)
            self.listening_started.emit()

            try:
                audio = self.speech_service.listen()
                self.listening_ended.emit()

                if audio is not None and self._listen_enabled and self._is_running:
                    transcript = self.speech_service.speech_to_text(audio)
                    if transcript:
                        self.speech_recognized.emit(transcript)
            except Exception as e:
                self.listening_ended.emit()
                self.error_occurred.emit(f"Voice recognition error: {e}")
                self.msleep(200)


class CommandWorker(QThread):
    """
    Background worker thread for processing assistant commands.
    Executes assistant routing, conversational AI, web searches, and desktop actions.
    """
    status_changed = Signal(str)
    speech_output = Signal(str)
    command_started = Signal(str)
    command_finished = Signal(bool)
    confirmation_requested = Signal(str, str)  # (action_type, prompt_message)
    error_occurred = Signal(str)

    def __init__(self, assistant, parent=None):
        super().__init__(parent)
        self.assistant = assistant
        self._queue = Queue()
        self._is_running = True

        # Hook into tts speech stream so spoken responses emit directly to GUI
        tts.add_speech_listener(self._on_speech_emitted)

    def _on_speech_emitted(self, message: str):
        self.status_changed.emit(AssistantState.SPEAKING.value)
        self.speech_output.emit(message)

    def post_command(self, text: str, direct: bool = True):
        """Enqueue a command for the assistant to process."""
        self._queue.put((text, direct))

    def stop(self):
        self._is_running = False
        tts.remove_speech_listener(self._on_speech_emitted)
        self.wait(1500)

    def run(self):
        while self._is_running:
            try:
                item = self._queue.get(timeout=0.2)
            except Empty:
                continue

            if not item or not self._is_running:
                continue

            command, direct = item if isinstance(item, tuple) else (item, True)
            if not command:
                continue

            self.command_started.emit(command)
            self.status_changed.emit(AssistantState.THINKING.value)

            try:
                # Intercept dangerous actions that require UI confirmation if pending
                before_pending = getattr(self.assistant, "pending_confirmation", None)

                # Execute assistant logic
                success = self.assistant.handle(command, direct_command=direct)

                # Check if a confirmation was prompted
                after_pending = getattr(self.assistant, "pending_confirmation", None)
                if after_pending and after_pending != before_pending:
                    prompt = (
                        "Are you sure you want to shut down the computer?"
                        if after_pending == "shutdown"
                        else "Are you sure you want to close the current window?"
                    )
                    self.confirmation_requested.emit(after_pending, prompt)

                self.command_finished.emit(bool(success))
            except Exception as e:
                self.error_occurred.emit(f"Assistant processing error: {e}")
                self.command_finished.emit(False)
            finally:
                time.sleep(0.3)
                self.status_changed.emit(AssistantState.IDLE.value)
