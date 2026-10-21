"""Central configuration for MARUTI Desktop Assistant.

Reads configuration from environment variables and an optional .env file.
Provides paths, thresholds, safety constants, and hardware defaults.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

# Attempt to load .env if python-dotenv is installed
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Base filesystem directories
BASE_DIR: Path = Path(__file__).resolve().parent
LOGS_DIR: Path = BASE_DIR / "logs"
EVAL_DIR: Path = BASE_DIR / "eval"
DOCS_DIR: Path = BASE_DIR / "docs"

# Cloud & AI Settings (Optional Gemini Integration)
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_ENABLED: bool = bool(GEMINI_API_KEY)

# Location & Local Defaults
DEFAULT_CITY: str = os.getenv("MARUTI_CITY", "Boisar").strip()

# Perception / OCR Settings
TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "").strip()

# Soft-Computing Decision Thresholds
# Score >= ACT_THRESHOLD -> Execute immediately (ACT)
# ASK_THRESHOLD <= Score < ACT_THRESHOLD -> Clarify with user (ASK)
# Score < ASK_THRESHOLD -> Reject or re-analyze (RE_ANALYZE)
ACT_THRESHOLD: float = float(os.getenv("MARUTI_ACT_THRESHOLD", "0.85"))
ASK_THRESHOLD: float = float(os.getenv("MARUTI_ASK_THRESHOLD", "0.60"))

# Voice Pipeline Settings
DEFAULT_STT_LANG: str = os.getenv("MARUTI_STT_LANG", "en-IN").strip()
SECONDARY_STT_LANG: str = os.getenv("MARUTI_STT_SECONDARY_LANG", "hi-IN").strip()
STT_ENERGY_THRESHOLD: int = int(os.getenv("MARUTI_STT_ENERGY_THRESHOLD", "300"))
STT_DYNAMIC_ENERGY: bool = os.getenv("MARUTI_STT_DYNAMIC_ENERGY", "true").strip().lower() in ("true", "1", "yes")
STT_PAUSE_THRESHOLD: float = float(os.getenv("MARUTI_STT_PAUSE_THRESHOLD", "0.8"))
STT_NON_SPEAKING_DURATION: float = float(os.getenv("MARUTI_STT_NON_SPEAKING_DURATION", "0.5"))
STT_TIMEOUT: float = float(os.getenv("MARUTI_STT_TIMEOUT", "5.0"))
STT_PHRASE_LIMIT: float = float(os.getenv("MARUTI_STT_PHRASE_LIMIT", "10.0"))
REVIEW_MODE: bool = os.getenv("MARUTI_REVIEW_MODE", "false").strip().lower() in ("true", "1", "yes")
TTS_ENGINE: str = os.getenv("MARUTI_TTS_ENGINE", "auto").strip().lower()
TTS_RATE: int = int(os.getenv("MARUTI_TTS_RATE", "175"))
TTS_VOLUME: float = float(os.getenv("MARUTI_TTS_VOLUME", "1.0"))

# Agent & Safety Settings
MAX_AGENT_STEPS: int = int(os.getenv("MARUTI_MAX_STEPS", "6"))
KILL_PHRASES: Tuple[str, ...] = (
    "maruti stop",
    "stop maruti",
    "ruko",
    "maruti ruko",
    "ruk jao",
    "cancel",
    "stop",
    "chup",
    "chup ho jao",
    "emergency stop",
)
ACTION_LOG_PATH: Path = LOGS_DIR / "actions.jsonl"


def ensure_directories() -> None:
    """Ensure runtime folders exist."""
    for directory in (LOGS_DIR, EVAL_DIR, DOCS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


ensure_directories()
