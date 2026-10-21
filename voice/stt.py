"""Speech-to-Text (STT) module for MARUTI Desktop Assistant.

Handles audio capture from hardware microphones with Google Web Speech recognition,
ambient noise calibration, device enumeration, Hindi & English language selection,
and graceful degradation when microphones or internet connectivity are absent.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import config
from doctor import suppress_c_stderr

logger = logging.getLogger(__name__)

try:
    import speech_recognition as sr
except ImportError:
    sr = None
    logger.warning("speech_recognition package not installed.")


class Listener:
    """Robust Speech-to-Text listener supporting device selection and bilingual recognition."""

    # Error taxonomy constants
    STATUS_SUCCESS = "success"
    STATUS_NO_MIC = "no_microphone"
    STATUS_DEVICE_ERROR = "device_error"
    STATUS_TIMEOUT = "timeout"
    STATUS_UNINTELLIGIBLE = "unintelligible"
    STATUS_NETWORK_ERROR = "network_error"
    STATUS_CANCELLED = "cancelled"

    def __init__(
        self,
        device_index: Optional[int] = None,
        language: str = config.DEFAULT_STT_LANG,
        energy_threshold: int = config.STT_ENERGY_THRESHOLD,
        dynamic_energy: bool = config.STT_DYNAMIC_ENERGY,
        pause_threshold: float = config.STT_PAUSE_THRESHOLD,
        non_speaking_duration: float = config.STT_NON_SPEAKING_DURATION,
        dynamic_energy_adjustment_damping: float = 0.15,
        dynamic_energy_ratio: float = 1.5,
        is_speaking_check: Optional[Any] = None,
    ) -> None:
        """Initialize the speech recognition engine.

        Args:
            device_index: Hardware input device index (None for OS default).
            language: Primary recognition language code (e.g. 'en-IN', 'hi-IN').
            energy_threshold: Sensitivity threshold for silence/speech boundary.
            dynamic_energy: Whether to continuously adjust energy threshold.
            pause_threshold: Seconds of non-speaking audio before phrase is considered complete.
            non_speaking_duration: Seconds of non-speaking audio to retain on phrase sides.
            dynamic_energy_adjustment_damping: Rate at which dynamic energy threshold shifts.
            dynamic_energy_ratio: Multiplier above noise energy to consider speech.
            is_speaking_check: Optional callable returning True if TTS output is active.
        """
        self.device_index: Optional[int] = device_index
        self.language: str = language
        self.secondary_language: str = config.SECONDARY_STT_LANG
        self.recognizer: Optional[sr.Recognizer] = None
        self.microphone: Optional[sr.Microphone] = None
        self._mic_available: bool = False
        self._last_network_error: Optional[str] = None
        self._last_unexpected_error: Optional[str] = None
        self._last_capture_error: Optional[str] = None
        self._is_speaking_check = is_speaking_check
        self.last_status: str = "idle"
        self.last_diagnostic: Optional[str] = None
        self._cancel_requested: bool = False

        if sr is not None:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = energy_threshold
            self.recognizer.dynamic_energy_threshold = dynamic_energy
            self.recognizer.pause_threshold = pause_threshold
            self.recognizer.non_speaking_duration = non_speaking_duration
            self.recognizer.dynamic_energy_adjustment_damping = dynamic_energy_adjustment_damping
            self.recognizer.dynamic_energy_ratio = dynamic_energy_ratio
            self._init_microphone()

    def _reset_error_state(self) -> None:
        """Reset deduplication state after a successful recognition."""
        self._last_network_error = None
        self._last_unexpected_error = None
        self._last_capture_error = None

    def _init_microphone(self) -> bool:
        """Initialize and preserve a long-lived microphone device instance."""
        if sr is None:
            self._mic_available = False
            self.microphone = None
            return False

        try:
            with suppress_c_stderr():
                # Attempt to probe and preserve long-lived device instance
                self.microphone = sr.Microphone(device_index=self.device_index)
                with self.microphone:
                    pass
            self._mic_available = True
            return True
        except Exception as exc:
            logger.debug("Microphone initialization failed (%s: %s)", type(exc).__name__, exc)
            self._mic_available = False
            self.microphone = None
            return False

    def cancel(self) -> None:
        """Request cancellation of any pending or ongoing capture."""
        self._cancel_requested = True

    def reset_cancel(self) -> None:
        """Clear cancellation request flag."""
        self._cancel_requested = False

    @property
    def is_available(self) -> bool:
        """Return True if an audio input device is ready for capture."""
        return self._mic_available

    def get_diagnostics(self) -> Dict[str, Any]:
        """Return runtime audio and speech recognition diagnostics."""
        diag: Dict[str, Any] = {
            "mic_available": self._mic_available,
            "device_index": self.device_index,
            "language": self.language,
            "secondary_language": self.secondary_language,
            "last_status": self.last_status,
            "last_diagnostic": self.last_diagnostic,
        }
        if self.recognizer:
            diag.update({
                "energy_threshold": getattr(self.recognizer, "energy_threshold", None),
                "dynamic_energy_threshold": getattr(self.recognizer, "dynamic_energy_threshold", None),
                "pause_threshold": getattr(self.recognizer, "pause_threshold", None),
                "non_speaking_duration": getattr(self.recognizer, "non_speaking_duration", None),
            })
        return diag

    @staticmethod
    def list_microphones() -> List[Dict[str, Any]]:
        """Enumerate available audio input devices safely.

        Returns:
            List of dicts containing 'index' and 'name' of each microphone.
        """
        if sr is None:
            logger.warning("speech_recognition is unavailable.")
            return []

        try:
            with suppress_c_stderr():
                device_names = sr.Microphone.list_microphone_names()
            return [{"index": idx, "name": name} for idx, name in enumerate(device_names)]
        except Exception as exc:
            logger.warning("Failed to enumerate microphones: %s", exc)
            return []

    def calibrate_ambient_noise(self, duration: float = 0.5) -> bool:
        """Adjust background noise energy threshold to improve recognition accuracy.

        Args:
            duration: Calibration sampling duration in seconds.

        Returns:
            bool: True if calibration succeeded, False otherwise.
        """
        if not self._mic_available or self.recognizer is None or sr is None:
            return False

        try:
            with suppress_c_stderr():
                mic = self.microphone or sr.Microphone(device_index=self.device_index)
                with mic as source:
                    logger.info("Calibrating ambient noise for %.1f seconds...", duration)
                    self.recognizer.adjust_for_ambient_noise(source, duration=duration)
            return True
        except Exception as exc:
            logger.warning("Ambient noise calibration failed: %s", exc)
            return False

    def listen_with_diagnostics(
        self,
        timeout: Optional[float] = 5.0,
        phrase_time_limit: Optional[float] = 10.0,
        language: Optional[str] = None,
    ) -> Tuple[Optional[str], float, str, Optional[str]]:
        """Capture an audio phrase and transcribe it with explicit failure taxonomy.

        Returns:
            Tuple of (text, confidence, status_code, diagnostic_message).
        """
        if self._cancel_requested:
            self._cancel_requested = False
            self.last_status = self.STATUS_CANCELLED
            self.last_diagnostic = "Listening cancelled by user."
            return None, 0.0, self.STATUS_CANCELLED, self.last_diagnostic

        # Self-listening guard: do not capture while TTS is speaking
        if self._is_speaking_check:
            try:
                if callable(self._is_speaking_check) and self._is_speaking_check():
                    logger.debug("TTS active; paused listening capture.")
                    return None, 0.0, "tts_active", "Audio capture paused while speaking."
            except Exception:
                pass

        if not self._mic_available or self.recognizer is None or sr is None:
            logger.warning("Microphone is not available for listening.")
            self.last_status = self.STATUS_NO_MIC
            self.last_diagnostic = "No microphone input device detected."
            return None, 0.0, self.STATUS_NO_MIC, self.last_diagnostic

        lang = language or self.language

        try:
            with suppress_c_stderr():
                mic = self.microphone or sr.Microphone(device_index=self.device_index)
                with mic as source:
                    logger.debug("Listening for audio input...")
                    audio = self.recognizer.listen(
                        source,
                        timeout=timeout,
                        phrase_time_limit=phrase_time_limit,
                    )

            if self._cancel_requested:
                self._cancel_requested = False
                self.last_status = self.STATUS_CANCELLED
                self.last_diagnostic = "Capture cancelled after recording."
                return None, 0.0, self.STATUS_CANCELLED, self.last_diagnostic

            text, conf = self.transcribe_audio(audio, language=lang)
            if text:
                self.last_status = self.STATUS_SUCCESS
                self.last_diagnostic = f"Transcribed '{text}' with confidence {conf:.2f}"
                return text, conf, self.STATUS_SUCCESS, self.last_diagnostic
            else:
                self.last_status = self.STATUS_UNINTELLIGIBLE
                self.last_diagnostic = "Speech was detected but could not be understood."
                return None, 0.0, self.STATUS_UNINTELLIGIBLE, self.last_diagnostic

        except sr.WaitTimeoutError:
            logger.debug("Speech recognition timed out waiting for speech.")
            self.last_status = self.STATUS_TIMEOUT
            self.last_diagnostic = f"No speech detected within {timeout}s timeout."
            return None, 0.0, self.STATUS_TIMEOUT, self.last_diagnostic
        except sr.RequestError as exc:
            err_msg = str(exc)
            self.last_status = self.STATUS_NETWORK_ERROR
            self.last_diagnostic = f"Speech service network error: {exc}"
            if err_msg != self._last_network_error:
                logger.warning("Speech service network error: %s", exc)
                self._last_network_error = err_msg
            return None, 0.0, self.STATUS_NETWORK_ERROR, self.last_diagnostic
        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}"
            self.last_status = self.STATUS_DEVICE_ERROR
            self.last_diagnostic = f"Microphone device error: {exc}"
            if err_msg != self._last_capture_error:
                logger.warning("Audio capture encountered error: %s", exc)
                self._last_capture_error = err_msg
            else:
                logger.debug("Repeated audio capture error: %s", exc)
            return None, 0.0, self.STATUS_DEVICE_ERROR, self.last_diagnostic

    def listen(
        self,
        timeout: Optional[float] = 5.0,
        phrase_time_limit: Optional[float] = 10.0,
        language: Optional[str] = None,
    ) -> Tuple[Optional[str], float]:
        """Capture an audio phrase and transcribe it using Google Web Speech.

        Preserves standard (text, confidence) interface for backward compatibility.
        """
        text, conf, _, _ = self.listen_with_diagnostics(
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
            language=language,
        )
        return text, conf

    def transcribe_audio(
        self,
        audio_data: Any,
        language: Optional[str] = None,
    ) -> Tuple[Optional[str], float]:
        """Transcribe an AudioData instance into text with confidence estimation.

        Args:
            audio_data: speech_recognition.AudioData instance.
            language: Language code to transcribe.

        Returns:
            Tuple of (text, confidence).
        """
        if self.recognizer is None or sr is None:
            return None, 0.0

        primary_lang = language or self.language

        # Attempt primary recognition
        text, conf = self._recognize_with_lang(audio_data, primary_lang)
        if text:
            return text, conf

        # If primary failed and secondary is configured (e.g. Hindi/Hinglish fallback)
        if self.secondary_language and primary_lang != self.secondary_language:
            text_sec, conf_sec = self._recognize_with_lang(
                audio_data, self.secondary_language
            )
            if text_sec:
                logger.info("Transcribed using fallback language (%s): '%s'", self.secondary_language, text_sec)
                return text_sec, conf_sec

        return None, 0.0

    def _recognize_with_lang(
        self, audio_data: Any, lang_code: str
    ) -> Tuple[Optional[str], float]:
        """Call Google Web Speech API for a specific language code."""
        try:
            # speech_recognition uses show_all=True to return the raw API response dictionary
            # containing alternative hypotheses and confidence scores.
            try:
                response = self.recognizer.recognize_google(
                    audio_data, language=lang_code, show_all=True
                )
            except TypeError:
                # Fallback if a custom/mock recognizer does not accept show_all
                response = self.recognizer.recognize_google(
                    audio_data, language=lang_code
                )

            if isinstance(response, dict) and "alternative" in response:
                alternatives = response.get("alternative", [])
                if alternatives:
                    # Pick hypothesis with highest confidence, or first if confidence omitted
                    best = alternatives[0]
                    for alt in alternatives:
                        if isinstance(alt, dict) and "confidence" in alt:
                            if float(alt["confidence"]) > float(best.get("confidence", 0.0)):
                                best = alt

                    if isinstance(best, dict):
                        transcript = str(best.get("transcript", "")).strip()
                        confidence = float(best.get("confidence", 0.88))
                    elif isinstance(best, str):
                        transcript = best.strip()
                        confidence = 0.88
                    else:
                        transcript = ""
                        confidence = 0.0

                    if transcript:
                        self._reset_error_state()
                        return transcript, confidence

            # Fallback if string is returned directly (e.g. show_all=False or single string)
            if isinstance(response, str) and response.strip():
                self._reset_error_state()
                return response.strip(), 0.88

            # Fallback if tuple of (transcript, confidence) is returned
            if isinstance(response, (list, tuple)) and len(response) == 2 and isinstance(response[0], str):
                self._reset_error_state()
                return response[0].strip(), float(response[1])

            return None, 0.0

        except sr.UnknownValueError:
            logger.debug("Google Web Speech could not understand audio for language %s.", lang_code)
            return None, 0.0
        except sr.RequestError as exc:
            err_msg = str(exc)
            if err_msg != self._last_network_error:
                logger.warning("Google Web Speech network service error: %s (will continue retrying)", exc)
                self._last_network_error = err_msg
            else:
                logger.debug("Repeated Google Web Speech service error: %s", exc)
            return None, 0.0
        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}"
            if err_msg != self._last_unexpected_error:
                logger.error("Unexpected error during speech transcription: %s", exc)
                self._last_unexpected_error = err_msg
            else:
                logger.debug("Repeated error during speech transcription: %s", exc)
            return None, 0.0
