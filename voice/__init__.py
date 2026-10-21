"""Voice processing package for MARUTI Desktop Assistant.

Provides Speech-to-Text (STT), Text-to-Speech (TTS), and Wake-Word Detection.
"""
from voice.stt import Listener
from voice.tts import Speaker
from voice.wake import WakeDetector

__all__ = ["Listener", "Speaker", "WakeDetector"]
