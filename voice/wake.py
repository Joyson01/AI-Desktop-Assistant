"""Wake-word and kill-phrase detection for MARUTI Desktop Assistant.

Detects multilingual wake phrases ('Hello Maruti', 'मारुति', 'Suno Maruti')
and emergency kill phrases ('Maruti stop', 'ruko', 'ruk jao').
Cleans and strips wake prefixes for downstream NLU routing.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)

# Wake word patterns: English, Hindi (Devanagari), and Hinglish transliterations
WAKE_PATTERNS = [
    # English & Hinglish variations
    r"\b(?:hello|hey|hi|ok|okay|suno|sun|are|o|namaste)\s+maruti\b",
    r"\bmaruti\s+(?:ji|bhai|sahab|sahib)\b",
    r"\bmaruti\b",
    # Hindi Devanagari variations
    r"(?:नमस्ते|हे|अरे|सुनो|सुनीये)\s*मारुति",
    r"मारुति\s*(?:जी)?",
    r"मारुति",
]

COMPILED_WAKE_REGEX = re.compile("|".join(WAKE_PATTERNS), re.IGNORECASE | re.UNICODE)


class WakeDetector:
    """Detects, extracts, and strips wake words and kill phrases."""

    def __init__(self, kill_phrases: Optional[tuple[str, ...]] = None) -> None:
        """Initialize wake and kill phrases."""
        self.kill_phrases = [
            phrase.lower().strip() for phrase in (kill_phrases or config.KILL_PHRASES)
        ]

    def has_wake(self, text: Optional[str]) -> bool:
        """Check if an utterance contains the MARUTI wake word.

        Args:
            text: Input string.

        Returns:
            bool: True if wake phrase is present.
        """
        if not text:
            return False
        return bool(COMPILED_WAKE_REGEX.search(text.strip()))

    def strip_wake(self, text: Optional[str]) -> str:
        """Remove wake phrases and leading/trailing punctuation from utterance.

        Args:
            text: Raw recognized speech or text input.

        Returns:
            str: Cleaned command string.
        """
        if not text:
            return ""

        cleaned = text.strip()

        # Remove wake word pattern
        cleaned = COMPILED_WAKE_REGEX.sub("", cleaned).strip()

        # Clean leading/trailing punctuation and common connector words (e.g. ',', 'please', 'kripya')
        cleaned = re.sub(r"^[\s,.:;!?-]+", "", cleaned)
        cleaned = re.sub(r"[\s,.:;!?-]+$", "", cleaned)

        # Strip polite leading words that might linger after wake word removal
        cleaned = re.sub(r"^(?:please|kripya|zara|kripaya)\s+", "", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    def is_kill_phrase(self, text: Optional[str]) -> bool:
        """Check if the user issued an emergency stop command.

        Args:
            text: Utterance to check.

        Returns:
            bool: True if command is a recognized kill phrase.
        """
        if not text:
            return False

        normalized = text.lower().strip()
        # Clean punctuation
        normalized = re.sub(r"[^\w\s]", "", normalized).strip()

        # Direct match or containment in configured kill phrases
        for phrase in self.kill_phrases:
            if phrase in normalized or normalized == phrase:
                return True

        return False
