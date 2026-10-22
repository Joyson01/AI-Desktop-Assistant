"""Unit tests for the Speech-to-Text (STT) module in MARUTI Desktop Assistant.

Tests cover:
- Listener initialization and language configuration (en-IN, hi-IN)
- Speech transcription with dict response (show_all=True)
- Speech transcription with string response fallback
- Bilingual fallback behavior (en-IN -> hi-IN)
- Unintelligible speech and silence handling (sr.UnknownValueError, sr.WaitTimeoutError)
- Error deduplication for network service errors (sr.RequestError)
- Error deduplication for unexpected exceptions
- Verification that show_dict is NOT used and show_all is supported
"""
import logging
from unittest.mock import MagicMock, patch
import pytest
import speech_recognition as sr
from voice.stt import Listener


@pytest.fixture
def listener():
    l = Listener(language="en-IN")
    l._mic_available = True
    l.microphone = MagicMock()
    return l


@pytest.fixture
def dummy_audio():
    # 1 second of 16kHz 16-bit mono PCM silence
    return sr.AudioData(b"\x00" * 32000, 16000, 2)


def test_listener_init_defaults(listener):
    """Verify listener initializes with configured languages."""
    assert listener.language == "en-IN"
    assert listener.secondary_language == "hi-IN"
    assert listener.recognizer is not None


def test_transcribe_audio_dict_with_confidence(listener, dummy_audio):
    """Verify transcription parses show_all dict with alternative and confidence."""
    listener.recognizer.recognize_google = MagicMock(return_value={
        "alternative": [
            {"transcript": "open chrome", "confidence": 0.96},
            {"transcript": "open Chrome", "confidence": 0.81},
        ],
        "final": True,
    })

    text, conf = listener.transcribe_audio(dummy_audio)
    assert text == "open chrome"
    assert conf == 0.96


def test_transcribe_audio_dict_without_confidence(listener, dummy_audio):
    """Verify transcription defaults confidence when Google API omits confidence."""
    listener.recognizer.recognize_google = MagicMock(return_value={
        "alternative": [{"transcript": "search youtube"}],
        "final": True,
    })

    text, conf = listener.transcribe_audio(dummy_audio)
    assert text == "search youtube"
    assert conf == 0.88


def test_transcribe_audio_string_fallback(listener, dummy_audio):
    """Verify transcription handles direct string return gracefully."""
    listener.recognizer.recognize_google = MagicMock(
        return_value="search youtube for python tutorials"
    )

    text, conf = listener.transcribe_audio(dummy_audio)
    assert text == "search youtube for python tutorials"
    assert conf == 0.88


def test_transcribe_audio_secondary_language_fallback(listener, dummy_audio):
    """Verify fallback to secondary language when primary language cannot understand audio."""
    def fake_recognize(audio, language, show_all=True):
        if language == "en-IN":
            raise sr.UnknownValueError()
        return {"alternative": [{"transcript": "chrome kholo", "confidence": 0.91}]}

    listener.recognizer.recognize_google = MagicMock(side_effect=fake_recognize)

    text, conf = listener.transcribe_audio(dummy_audio)
    assert text == "chrome kholo"
    assert conf == 0.91


def test_transcribe_audio_unintelligible(listener, dummy_audio):
    """Verify unintelligible speech returns (None, 0.0) without raising exceptions."""
    listener.recognizer.recognize_google = MagicMock(side_effect=sr.UnknownValueError())

    text, conf = listener.transcribe_audio(dummy_audio)
    assert text is None
    assert conf == 0.0


def test_network_error_deduplication(listener, dummy_audio):
    """Verify network errors log only once and do not flood the console on consecutive failures."""
    listener_logger = logging.getLogger("voice.stt")
    captured_warnings = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.WARNING:
                captured_warnings.append(record.getMessage())

    handler = CapturingHandler()
    listener_logger.addHandler(handler)
    try:
        listener.recognizer.recognize_google = MagicMock(
            side_effect=sr.RequestError("recognition connection failed: host unreachable")
        )

        for _ in range(5):
            res = listener.transcribe_audio(dummy_audio)
            assert res == (None, 0.0)

        # Should only have logged 1 warning across all attempts, not 5 or 10
        assert len(captured_warnings) == 1
        assert "host unreachable" in captured_warnings[0]
    finally:
        listener_logger.removeHandler(handler)


def test_unexpected_error_deduplication(listener, dummy_audio):
    """Verify unexpected transcription errors log once and do not flood on consecutive failures."""
    listener_logger = logging.getLogger("voice.stt")
    captured_errors = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                captured_errors.append(record.getMessage())

    handler = CapturingHandler()
    listener_logger.addHandler(handler)
    try:
        listener.recognizer.recognize_google = MagicMock(
            side_effect=RuntimeError("audio driver buffer glitch")
        )

        for _ in range(4):
            res = listener.transcribe_audio(dummy_audio)
            assert res == (None, 0.0)

        assert len(captured_errors) == 1
        assert "audio driver buffer glitch" in captured_errors[0]
    finally:
        listener_logger.removeHandler(handler)


def test_error_state_resets_after_success(listener, dummy_audio):
    """Verify error deduplication state resets so subsequent new errors are reported."""
    listener.recognizer.recognize_google = MagicMock(
        side_effect=sr.RequestError("temporary glitch")
    )
    listener.transcribe_audio(dummy_audio)
    assert listener._last_network_error == "temporary glitch"

    # Now recognition succeeds
    listener.recognizer.recognize_google = MagicMock(return_value="hello")
    text, _ = listener.transcribe_audio(dummy_audio)
    assert text == "hello"
    assert listener._last_network_error is None


def test_listen_silence_timeout(listener):
    """Verify listen() handles WaitTimeoutError without raising or logging errors."""
    with patch.object(listener.recognizer, "listen", side_effect=sr.WaitTimeoutError()):
        text, conf = listener.listen(timeout=1.0)
        assert text is None
        assert conf == 0.0


def test_listener_diagnostics(listener):
    """Verify diagnostics dictionary contains energy threshold and audio metadata."""
    diag = listener.get_diagnostics()
    assert "energy_threshold" in diag
    assert "dynamic_energy_threshold" in diag
    assert "language" in diag
    assert diag["language"] == "en-IN"
    assert "last_status" in diag


def test_listener_cancellation_before_capture():
    """Verify requesting cancellation returns STATUS_CANCELLED without capturing audio."""
    l = Listener(language="en-IN")
    l.cancel()
    text, conf, status, msg = l.listen_with_diagnostics(timeout=1.0)
    assert text is None
    assert status == Listener.STATUS_CANCELLED
    assert "cancelled" in msg.lower()


def test_listener_suppression_while_tts_speaking(dummy_audio):
    """Verify audio capture is suppressed while TTS is actively speaking."""
    is_speaking = True
    l = Listener(language="en-IN", is_speaking_check=lambda: is_speaking)
    l._mic_available = True
    l.microphone = MagicMock()
    text, conf, status, msg = l.listen_with_diagnostics(timeout=1.0)
    assert text is None
    assert status == "tts_active"

    # When speaking finishes, capture proceeds
    is_speaking = False
    with patch.object(l.recognizer, "listen", return_value=dummy_audio):
        with patch.object(l, "transcribe_audio", return_value=("hello", 0.95)):
            text, conf, status, msg = l.listen_with_diagnostics(timeout=1.0)
            assert text == "hello"
            assert status == Listener.STATUS_SUCCESS


def test_listen_with_diagnostics_taxonomy_unintelligible(listener, dummy_audio):
    """Verify unintelligible speech returns STATUS_UNINTELLIGIBLE with diagnostic message."""
    with patch.object(listener.recognizer, "listen", return_value=dummy_audio):
        with patch.object(listener, "transcribe_audio", return_value=(None, 0.0)):
            text, conf, status, msg = listener.listen_with_diagnostics(timeout=1.0)
            assert text is None
            assert status == Listener.STATUS_UNINTELLIGIBLE
            assert "could not be understood" in msg

