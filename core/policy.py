"""Safety Policy Engine for MARUTI Desktop Assistant.

Defines action risk classifications (SAFE vs SENSITIVE), validation schemas,
and strict confirmation gates. Ensures that LLM planning cannot downgrade
sensitive actions to safe.
"""
from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Set

logger = logging.getLogger("maruti.policy")


from core.models import ActionRisk


@dataclass
class ActionResult:
    """Standardized result returned by all action executions."""
    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    verification: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def __str__(self) -> str:
        return self.message


class PolicyEngine:
    """Enforces safety rules, confirmation gates, and risk classifications."""

    # Explicit list of sensitive intent names that MUST require human confirmation
    DEFAULT_SENSITIVE_INTENTS: Set[str] = {
        "close_window",
        "delete_file",
        "overwrite_file",
        "run_shell_command",
        "send_message",
        "send_email",
        "submit_form",
        "purchase",
        "payment",
        "change_security_settings",
        "browser_login",
        "browser_payment",
    }

    # Safe intents that can execute automatically when parameters are validated
    DEFAULT_SAFE_INTENTS: Set[str] = {
        "greet",
        "exit",
        "open",
        "open_folder",
        "web_search",
        "youtube",
        "volume_set",
        "volume_change",
        "volume_mute",
        "scroll",
        "nav",
        "new_tab",
        "close_tab",
        "minimize",
        "switch_window",
        "weather",
        "chat",
        "read_screen",
        "inspect_screen",
        "browser_click_video",
        "type_text",
        "press_keys",
        "caps",
        "hello_world",
        "open_and_type",
        "start_dictation",
        "stop_dictation",
    }

    def __init__(
        self,
        confirm_callback: Optional[Callable[[str], bool]] = None,
        sensitive_intents: Optional[Set[str]] = None,
    ) -> None:
        """Initialize PolicyEngine.

        Args:
            confirm_callback: Function prompting user for yes/no confirmation.
            sensitive_intents: Optional set overriding/extending sensitive intents.
        """
        self.confirm = confirm_callback or (lambda prompt: False)
        self.sensitive_intents = set(sensitive_intents or self.DEFAULT_SENSITIVE_INTENTS)

    def classify_risk(self, intent_name: str, args: Optional[Dict[str, Any]] = None) -> ActionRisk:
        """Deterministically determine if an action is SAFE or SENSITIVE.

        The model cannot override this classification.
        """
        if intent_name in self.sensitive_intents:
            return ActionRisk.SENSITIVE

        # Block arbitrary terminal / shell execution
        if intent_name in ("run_shell_command", "terminal", "bash", "shell", "cmd"):
            return ActionRisk.BLOCKED

        # Require confirmation for password / OTP / PIN text entry
        if intent_name in ("type_text", "open_and_type") and args:
            for val in args.values():
                val_str = str(val).lower()
                if re.search(r"\b(?:password|passwd|otp|pin|cvv|secret)\b", val_str):
                    return ActionRisk.SENSITIVE

        # Dynamic inspection: check for dangerous destructive patterns in arguments
        if args and intent_name not in ("web_search", "youtube", "chat"):
            # Check for disk format, file destruction, or shell command injection in args
            for val in args.values():
                val_str = str(val).lower()
                if re.search(r"\b(?:rm\s+-rf|mkfs(?:\.\w+)?|drop\s+table|format\s+[a-zA-Z]:)\b", val_str):
                    return ActionRisk.SENSITIVE

        return ActionRisk.SAFE

    def authorize_execution(
        self,
        intent_name: str,
        args: Optional[Dict[str, Any]] = None,
        custom_prompt: Optional[str] = None,
    ) -> bool:
        """Evaluate if an action is authorized to execute.

        If SAFE: returns True immediately.
        If SENSITIVE: prompts user via confirm_callback and returns result.
        """
        risk = self.classify_risk(intent_name, args)
        if risk == ActionRisk.SAFE:
            return True

        # SENSITIVE requires explicit confirmation
        prompt = custom_prompt or f"Action '{intent_name}' is sensitive. Do you want to proceed?"
        logger.info("Requesting confirmation for sensitive intent '%s'", intent_name)
        confirmed = self.confirm(prompt)
        if not confirmed:
            logger.info("User declined confirmation for '%s'", intent_name)
        return confirmed
