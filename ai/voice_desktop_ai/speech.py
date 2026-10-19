"""Backward-compatibility re-export for voice services."""
from voice.stt import SpeechService
from voice.speech_normalizer import normalize_command

__all__ = ["SpeechService", "normalize_command"]

