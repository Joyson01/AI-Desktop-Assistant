"""Structured, redacted action logger for MARUTI Desktop Assistant.

Maintains an append-only JSON Lines record in logs/actions.jsonl.
Strictly redacts passwords, credentials, OTPs, credit cards, and confidential tokens.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger("maruti.action_logger")

REDACTION_PATTERNS = [
    # Passwords & PINs
    (re.compile(r"(?i)\b(?:password|passwd|pwd|passcode|pin)\s*[:=]\s*\S+"), "[REDACTED_SECRET]"),
    # Credit/Debit cards (13-16 digits with spaces or hyphens)
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[REDACTED_CARD]"),
    # OTPs (4-8 digits labeled as otp/code)
    (re.compile(r"(?i)\b(?:otp|one[- ]time[- ]password|verification code)\s*[:=]?\s*\d{4,8}\b"), "[REDACTED_OTP]"),
    # API tokens / bearer tokens
    (re.compile(r"(?i)\b(?:bearer\s+[a-zA-Z0-9_\-\.]{15,}|token\s*[:=]\s*[a-zA-Z0-9_\-]{15,})"), "[REDACTED_TOKEN]"),
]

SENSITIVE_PARAM_KEYS = {
    "password", "passwd", "pwd", "pin", "otp", "token", "secret",
    "auth_token", "api_key", "card", "cvv", "credit_card",
}


def redact_text(text: Optional[str]) -> str:
    """Scrub sensitive patterns from text before logging."""
    if not text:
        return ""
    redacted = str(text)
    for pat, rep in REDACTION_PATTERNS:
        redacted = pat.sub(rep, redacted)
    return redacted


def redact_data(obj: Any) -> Any:
    """Recursively scrub sensitive keys and patterns from dicts/lists."""
    if isinstance(obj, dict):
        clean = {}
        for k, v in obj.items():
            if str(k).lower() in SENSITIVE_PARAM_KEYS:
                clean[k] = "[REDACTED]"
            else:
                clean[k] = redact_data(v)
        return clean
    elif isinstance(obj, list):
        return [redact_data(item) for item in obj]
    elif isinstance(obj, str):
        return redact_text(obj)
    return obj


class ActionLogger:
    """Thread-safe append-only logger for desktop actions."""

    def __init__(self, log_path: Optional[str] = None) -> None:
        if log_path:
            self.file_path = Path(log_path)
        else:
            self.file_path = Path(__file__).resolve().parent.parent / "logs" / "actions.jsonl"
        self._lock = threading.Lock()
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning("Could not create logs directory: %s", exc)

    def log_action(
        self,
        original_transcript: str,
        normalized_transcript: str,
        intent_name: str,
        args: Dict[str, Any],
        dry_run: bool,
        selected_backend: str,
        success: bool,
        message: str,
        verification_level: str = "unverifiable",
        verification_details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an executed action entry to actions.jsonl safely."""
        now = datetime.now(timezone.utc)
        record = {
            "timestamp": now.isoformat(),
            "timestamp_epoch": now.timestamp(),
            "original_transcript": redact_text(original_transcript),
            "normalized_transcript": redact_text(normalized_transcript),
            "intent": {
                "name": intent_name,
                "args": redact_data(args),
            },
            "dry_run": bool(dry_run),
            "backend": selected_backend,
            "outcome": {
                "success": bool(success),
                "message": redact_text(message),
            },
            "verification": {
                "level": verification_level,
                "details": redact_data(verification_details or {}),
            },
            "error": redact_text(error) if error else None,
        }

        with self._lock:
            try:
                with open(self.file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception as exc:
                logger.error("Failed to write to action log: %s", exc)

        return record
