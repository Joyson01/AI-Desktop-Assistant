"""Assistant — Unified Route and Execute Façade for MARUTI Desktop Assistant.

Serves as the single coordinator for CLI, Hands-Free Voice, and PySide6 GUI:
- Enforces strict state machine serialization (IDLE -> ROUTING -> EXECUTING -> IDLE).
- Produces typed ActionPlan and ExecutionResult models.
- Audits all actions to structured local JSONL logs with automatic credential redaction.
- Manages human-in-the-loop confirmation gates for sensitive operations.
- Provides immediate, thread-safe cancellation and stop handling.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from actions import ActionExecutor
from brain import Brain
import config
from core.action_logger import ActionLogger
from core.capabilities import detect_capabilities
from core.context import ConversationContext
from core.models import (
    ActionPlan,
    ActionRisk,
    ActionStep,
    AssistantState,
    BackendCapability,
    ExecutionContext,
    ExecutionResult,
    ParsedIntent,
    Transcript,
    VerificationLevel,
    VerificationResult,
)
from core.policy import PolicyEngine
from core.state import AssistantStateMachine, StateListener, StateTransitionError
from intent_router import IntentRouter
from voice.stt import Listener
from voice.tts import Speaker
from voice.wake import WakeDetector

logger = logging.getLogger("maruti.assistant")

EXIT_PHRASES = {
    "exit", "quit", "bye", "goodbye", "alvida", "band karo",
    "stop listening", "exit assistant", "quit assistant",
    "stop assistant", "close assistant",
}

KILL_PHRASES = {
    "maruti stop", "stop maruti", "ruko", "maruti ruko",
    "ruk jao", "cancel", "chup", "chup ho jao", "emergency stop", "stop",
}


class Assistant:
    """Unified route and execution façade for MARUTI."""

    def __init__(
        self,
        dry_run: bool = False,
        mute: bool = False,
        mic_index: Optional[int] = None,
        language: str = config.DEFAULT_STT_LANG,
        confirm_callback: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.dry_run = dry_run
        self.mute = mute
        self.language = language

        # Core subsystems
        self.state_machine = AssistantStateMachine()
        self.action_logger = ActionLogger()
        self.capabilities = detect_capabilities()
        self.context = ConversationContext()
        self.wake_detector = WakeDetector()
        self.router = IntentRouter()
        self.confirm_callback = confirm_callback

        self.speaker = Speaker(enabled=not mute)
        self.listener = Listener(device_index=mic_index, language=language)

        self.policy = PolicyEngine(confirm_callback=self._handle_confirmation)
        self.executor = ActionExecutor(
            Brain(),
            dry_run=dry_run,
            confirm=self._handle_confirmation,
            context=self.context,
        )

        logger.info(
            "Assistant initialized (Session=%s, DryRun=%s, Mute=%s, Lang=%s)",
            self.capabilities.session_type,
            self.dry_run,
            self.mute,
            self.language,
        )

    # ---- State & Listener Management -----------------------------------
    @property
    def state(self) -> AssistantState:
        return self.state_machine.current_state

    def add_state_listener(self, callback: StateListener) -> None:
        self.state_machine.add_listener(callback)

    def remove_state_listener(self, callback: StateListener) -> None:
        self.state_machine.remove_listener(callback)

    def cancel(self, reason: str = "User requested stop") -> None:
        """Immediately stop speaking, listening, and queued execution."""
        self.speaker.stop()
        self.state_machine.request_cancel(reason)
        self.speaker.say("Stopping immediately.", block=False)

    def _handle_confirmation(self, prompt: str) -> bool:
        """Mediate confirmation request through state machine and UI callback."""
        self.state_machine.transition_to(
            AssistantState.AWAITING_CONFIRMATION,
            message=prompt,
            force=True,
        )
        if self.confirm_callback:
            confirmed = self.confirm_callback(prompt)
        else:
            confirmed = False
        return confirmed

    # ---- Action Planning -----------------------------------------------
    def plan_command(self, raw_text: str, dry_run: Optional[bool] = None) -> ActionPlan:
        """Parse raw text, evaluate safety policy, and generate structured ActionPlan."""
        is_dry = self.dry_run if dry_run is None else dry_run
        clean_text = self.wake_detector.strip_wake(raw_text.strip())

        intent = self.router.route(clean_text, context=self.context)
        risk = self.policy.classify_risk(intent.name, intent.args)

        # Check if platform capabilities block this action
        if intent.name in ("read_screen", "inspect_screen", "click") and not self.capabilities.has_tesseract:
            risk = ActionRisk.BLOCKED

        prompt = None
        if risk == ActionRisk.SENSITIVE:
            prompt = f"Action '{intent.name}' is sensitive. Do you want to proceed?"
        elif intent.is_ambiguous or (0.55 <= intent.confidence < config.ACT_THRESHOLD):
            risk = ActionRisk.SENSITIVE
            label = intent.args.get("label", intent.name)
            prompt = intent.clarification_prompt or f"I am not entirely sure. Did you mean {label}?"
        elif intent.confidence < 0.55 and intent.name not in ("chat", "empty", "greet", "unknown"):
            risk = ActionRisk.BLOCKED
            prompt = "I did not catch that clearly. Could you please rephrase?"

        target_app = self.context.target_app
        if intent.name in ("open", "open_and_type"):
            target_app = intent.args.get("target") or intent.args.get("app")

        step = ActionStep(
            action_name=intent.name,
            params=intent.args,
            description=f"Execute {intent.name} with {intent.args}",
            risk=risk,
        )

        plan = ActionPlan(
            intent=ParsedIntent(
                name=intent.name,
                args=intent.args,
                confidence=intent.confidence,
                raw=raw_text,
                is_ambiguous=intent.is_ambiguous,
                clarification_prompt=prompt,
            ),
            steps=[step],
            risk=risk,
            confirmation_prompt=prompt,
            target_app=target_app,
            requires_focus=intent.name in ("type_text", "press_keys", "select_line", "select_all", "clipboard_cut", "clipboard_paste", "delete_selected", "edit_undo", "edit_redo"),
            dry_run=is_dry,
        )
        return plan

    # ---- Action Execution ----------------------------------------------
    def execute_plan(self, plan: ActionPlan) -> ExecutionResult:
        """Execute a validated ActionPlan under state machine serialization."""
        self.state_machine.transition_to(AssistantState.EXECUTING, message=plan.intent.name)
        self.state_machine.set_active_plan(plan)

        try:
            # Check cancellation before proceeding
            if self.state_machine.is_cancelled:
                res = ExecutionResult(
                    success=False,
                    message="Action cancelled.",
                    intent_name=plan.intent.name,
                    plan=plan,
                    verification=VerificationResult(VerificationLevel.BLOCKED, False, "Cancelled by user."),
                )
                self.state_machine.transition_to(AssistantState.IDLE, message="Cancelled")
                return res

            # Handle BLOCKED risk tier
            if plan.risk == ActionRisk.BLOCKED:
                reason = plan.confirmation_prompt or (
                    "Capability blocked: Tesseract OCR is not installed."
                    if plan.intent.name in ("read_screen", "inspect_screen", "click")
                    else f"Action '{plan.intent.name}' is blocked by policy."
                )
                res = ExecutionResult(
                    success=False,
                    message=reason,
                    intent_name=plan.intent.name,
                    plan=plan,
                    verification=VerificationResult(VerificationLevel.BLOCKED, False, reason),
                )
                self.speaker.say(reason)
                self.state_machine.transition_to(AssistantState.IDLE, message="Blocked")
                return res

            # Handle SENSITIVE confirmation gate
            if plan.risk == ActionRisk.SENSITIVE:
                confirmed = self._handle_confirmation(
                    plan.confirmation_prompt or f"Confirm '{plan.intent.name}'?"
                )
                if not confirmed:
                    self.action_logger.log_action(
                        original_transcript=plan.intent.raw,
                        normalized_transcript=plan.intent.name,
                        intent_name=plan.intent.name,
                        args=plan.intent.args,
                        dry_run=plan.dry_run,
                        selected_backend=self.capabilities.session_type,
                        success=False,
                        message="Action cancelled by user.",
                        verification_level=VerificationLevel.BLOCKED.value,
                    )
                    res = ExecutionResult(
                        success=False,
                        message="Action cancelled by user.",
                        intent_name=plan.intent.name,
                        plan=plan,
                        verification=VerificationResult(VerificationLevel.BLOCKED, False, "User declined confirmation."),
                    )
                    self.speaker.say("Action cancelled.")
                    self.state_machine.transition_to(AssistantState.IDLE, message="Declined")
                    return res

            # Synchronize executor dry-run state with the plan
            self.executor.dry_run = plan.dry_run
            if hasattr(self.executor, "registry") and self.executor.registry:
                self.executor.registry.dry_run = plan.dry_run

            # Execute via ActionExecutor
            reply = self.executor.execute(plan.intent)
            lower_reply = reply.lower()
            is_failure = (
                lower_reply.startswith("sorry, that failed")
                or lower_reply.startswith("could not find")
                or lower_reply.startswith("multiple elements")
                or lower_reply.startswith("click failed")
                or lower_reply.startswith("target coordinates")
                or lower_reply.startswith("could not capture")
                or lower_reply.startswith("cancelled clicking")
            )
            success = not is_failure

            # Determine verification level
            verif_level = (
                VerificationLevel.PLANNED if plan.dry_run
                else VerificationLevel.POSTCONDITION_VERIFIED if success and plan.intent.name in ("volume_set", "volume_mute", "open")
                else VerificationLevel.ISSUED if success
                else VerificationLevel.FAILED
            )

            verif = VerificationResult(
                level=verif_level,
                success=success,
                message=f"Verification level: {verif_level.value}",
                details={"target_app": plan.target_app, "dry_run": plan.dry_run},
            )

            # Record in context
            self.context.update_action(plan.intent.name, reply)

            # Audit log
            self.action_logger.log_action(
                original_transcript=plan.intent.raw,
                normalized_transcript=plan.intent.name,
                intent_name=plan.intent.name,
                args=plan.intent.args,
                dry_run=plan.dry_run,
                selected_backend=self.capabilities.session_type,
                success=success,
                message=reply,
                verification_level=verif_level.value,
                verification_details=verif.details,
            )

            # Speak outcome
            self.speaker.say(reply)

            res = ExecutionResult(
                success=success,
                message=reply,
                intent_name=plan.intent.name,
                plan=plan,
                verification=verif,
                data={"reply": reply, "dry_run": plan.dry_run},
            )
            self.state_machine.transition_to(AssistantState.IDLE, message="Finished")
            return res

        except Exception as exc:
            logger.exception("Error during execution of plan %s", plan.intent.name)
            error_msg = f"Sorry, that failed: {exc}"
            self.speaker.say(error_msg)
            self.state_machine.transition_to(AssistantState.ERROR, message=str(exc), force=True)
            self.state_machine.transition_to(AssistantState.IDLE, message="Recovered from error", force=True)
            return ExecutionResult(
                success=False,
                message=error_msg,
                intent_name=plan.intent.name,
                plan=plan,
                error=str(exc),
            )

    # ---- High-Level Facade Command Processing --------------------------
    def process(self, raw_input: str, dry_run: Optional[bool] = None) -> ExecutionResult:
        """Alias for process_text for unified facade callers."""
        return self.process_text(raw_input, dry_run=dry_run)

    def process_text(self, raw_input: str, dry_run: Optional[bool] = None) -> ExecutionResult:
        """Route, plan, safety-check, and execute a text or transcribed voice command."""
        if not raw_input or not raw_input.strip():
            return ExecutionResult(success=True, message="", intent_name="empty")

        text = raw_input.strip()
        text_lower = text.lower()
        clean_text = self.wake_detector.strip_wake(text)

        # 1. Emergency kill / stop check
        if text_lower in KILL_PHRASES or clean_text.lower() in KILL_PHRASES:
            self.cancel("Kill phrase spoken")
            return ExecutionResult(
                success=True,
                message="Stopping immediately.",
                intent_name="cancel",
                verification=VerificationResult(VerificationLevel.ISSUED, True, "Cancelled."),
            )

        # 2. Clean exit check
        if text_lower in EXIT_PHRASES or clean_text.lower() in EXIT_PHRASES:
            self.speaker.say("Goodbye! Have a productive day.", block=True)
            return ExecutionResult(
                success=True,
                message="Goodbye! Have a productive day.",
                intent_name="exit",
                data={"should_exit": True},
            )

        # 3. Duplicate command suppression
        if self.context.is_duplicate_submission(clean_text):
            logger.info("Suppressed duplicate voice submission: '%s'", clean_text)
            return ExecutionResult(
                success=True,
                message="Duplicate command suppressed.",
                intent_name="duplicate_suppressed",
            )

        # 4. Synchronize desktop window state before routing follow-ups
        self.context.sync_desktop_state()

        # 5. Transition to ROUTING
        try:
            self.state_machine.transition_to(AssistantState.ROUTING, message=clean_text)
        except StateTransitionError as err:
            logger.warning("Rejecting overlapping action: %s", err)
            return ExecutionResult(
                success=False,
                message=str(err),
                intent_name="busy",
            )

        # 6. Plan and Execute
        plan = self.plan_command(text, dry_run=dry_run)
        return self.execute_plan(plan)

    def shutdown(self) -> None:
        """Cleanly release speaker and speech threads."""
        self.cancel("Assistant shutdown")
        if self.speaker:
            self.speaker.close()
