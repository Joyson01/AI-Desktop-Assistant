"""Text-to-Speech (TTS) engine for MARUTI Desktop Assistant.

Provides cross-platform speech synthesis:
- Linux: spd-say (speech-dispatcher) / espeak-ng / pyttsx3 fallback.
- Windows: pyttsx3 with SAPI5 native driver.
- Graceful degradation: Console output if audio hardware is absent.
- Thread-safe background queuing so UI and agent loops are never blocked.
"""
from __future__ import annotations

import logging
import platform
import queue
import shutil
import subprocess
import threading
import time
from typing import Optional

import config

logger = logging.getLogger(__name__)


class Speaker:
    """Cross-platform, non-blocking text-to-speech speaker."""

    def __init__(
        self,
        enabled: bool = True,
        engine_type: Optional[str] = None,
        rate: int = config.TTS_RATE,
        volume: float = config.TTS_VOLUME,
    ) -> None:
        """Initialize TTS speaker.

        Args:
            enabled: False if speech output is muted.
            engine_type: 'auto', 'spd-say', 'espeak-ng', 'pyttsx3', or 'console'.
            rate: Speech rate in words-per-minute (approximate).
            volume: Speech volume between 0.0 and 1.0.
        """
        self.enabled: bool = enabled
        self.rate: int = rate
        self.volume: float = volume
        self.system: str = platform.system()
        self.engine_type: str = engine_type or config.TTS_ENGINE

        self.is_speaking: bool = False
        self.last_spoken: str = ""
        self.last_spoken_time: float = 0.0

        self._active_engine: str = self._resolve_engine()
        self._speech_queue: queue.Queue[tuple[str, bool, Optional[threading.Event]]] = queue.Queue()
        self._stop_event: threading.Event = threading.Event()
        self._current_process: Optional[subprocess.Popen] = None
        self._worker_thread: threading.Thread = threading.Thread(
            target=self._speech_loop, daemon=True, name="MARUTI-TTS-Worker"
        )
        self._worker_thread.start()
        logger.info("Speaker initialized using engine: %s (enabled=%s)", self._active_engine, self.enabled)

    def _resolve_engine(self) -> str:
        """Select the most suitable speech engine for the platform."""
        if self.engine_type != "auto":
            return self.engine_type

        if self.system == "Linux":
            if shutil.which("spd-say"):
                return "spd-say"
            if shutil.which("espeak-ng"):
                return "espeak-ng"
            if shutil.which("espeak"):
                return "espeak"

        try:
            import pyttsx3  # noqa: F401

            return "pyttsx3"
        except Exception:
            return "console"

    def say(self, text: str, block: bool = False) -> None:
        """Queue text to be spoken.

        Args:
            text: String utterance to speak.
            block: If True, waits until speech completes before returning.
        """
        clean_text = text.strip()
        if not clean_text:
            return

        if not self.enabled:
            logger.info("[MUTED] %s", clean_text)
            print(f"[MARUTI Muted]: {clean_text}")
            return

        if block:
            done_event = threading.Event()
            self._speech_queue.put((clean_text, True, done_event))
            done_event.wait()
        else:
            self._speech_queue.put((clean_text, False, None))

    def stop(self) -> None:
        """Halt speech playback immediately and purge queued phrases."""
        # Clear queue
        while not self._speech_queue.empty():
            try:
                _, _, evt = self._speech_queue.get_nowait()
                if evt:
                    evt.set()
                self._speech_queue.task_done()
            except queue.Empty:
                break

        # Terminate active process if running
        if self._current_process and self._current_process.poll() is None:
            try:
                self._current_process.terminate()
            except Exception:
                pass

        if self._active_engine == "spd-say" and shutil.which("spd-say"):
            try:
                subprocess.run(["spd-say", "-S"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def mute(self) -> None:
        """Mute voice output."""
        self.enabled = False
        self.stop()

    def unmute(self) -> None:
        """Enable voice output."""
        self.enabled = True

    def close(self) -> None:
        """Cleanly shut down the background speech worker thread."""
        self.stop()
        self._stop_event.set()
        self._speech_queue.put(("", False, None))

    def _speech_loop(self) -> None:
        """Background worker loop consuming phrases from the speech queue."""
        while not self._stop_event.is_set():
            try:
                text, is_blocking, done_event = self._speech_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if self._stop_event.is_set() or not text:
                if done_event:
                    done_event.set()
                self._speech_queue.task_done()
                break

            try:
                self._synthesize(text)
            except Exception as exc:
                logger.warning("TTS synthesis error (%s): %s. Falling back to console.", self._active_engine, exc)
                print(f"[MARUTI Voice]: {text}")
            finally:
                if done_event:
                    done_event.set()
                self._speech_queue.task_done()

    def _synthesize(self, text: str) -> None:
        """Execute platform-specific synthesis."""
        self.is_speaking = True
        self.last_spoken = text
        self.last_spoken_time = time.time()
        print(f"[MARUTI Speaking]: {text}")
        try:
            self._do_synthesize(text)
        finally:
            self.is_speaking = False

    def _do_synthesize(self, text: str) -> None:

        if self._active_engine == "spd-say" and shutil.which("spd-say"):
            # spd-say rate offset from -100 to 100
            rate_offset = max(-100, min(100, int((self.rate - 175) * 1.5)))
            cmd = ["spd-say", "-w", "-r", str(rate_offset), text]
            self._current_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._current_process.wait()
            self._current_process = None
            return

        if self._active_engine in ("espeak-ng", "espeak") and (shutil.which("espeak-ng") or shutil.which("espeak")):
            bin_name = "espeak-ng" if shutil.which("espeak-ng") else "espeak"
            cmd = [bin_name, "-s", str(self.rate), text]
            self._current_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._current_process.wait()
            self._current_process = None
            return

        if self._active_engine == "pyttsx3":
            try:
                import pyttsx3

                engine = pyttsx3.init()
                engine.setProperty("rate", self.rate)
                engine.setProperty("volume", self.volume)
                engine.say(text)
                engine.runAndWait()
                del engine
                return
            except Exception as exc:
                logger.debug("pyttsx3 failed in thread: %s. Using console output.", exc)

        # Ultimate fallback: printed output
        pass
