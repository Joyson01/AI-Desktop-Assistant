"""Central State Machine & Execution Serializer for MARUTI Desktop Assistant.

Ensures:
- Strict state tracking: IDLE, LISTENING, TRANSCRIBING, ROUTING, AWAITING_CONFIRMATION, EXECUTING, CANCELLED, ERROR.
- Non-overlapping execution serialization (prevents race conditions across voice & GUI threads).
- Immediate, thread-safe cancellation and stop flags.
- Real-time status event distribution to GUI/CLI listeners.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional

from core.models import ActionPlan, AssistantState

logger = logging.getLogger("maruti.state")

StateListener = Callable[[AssistantState, AssistantState, Optional[str]], None]


class StateTransitionError(Exception):
    """Raised when an invalid or overlapping state transition is attempted."""
    pass


class AssistantStateMachine:
    """Thread-safe coordinator managing assistant lifecycle states and serialization."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state: AssistantState = AssistantState.IDLE
        self._active_plan: Optional[ActionPlan] = None
        self._cancel_event = threading.Event()
        self._listeners: List[StateListener] = []

    @property
    def current_state(self) -> AssistantState:
        with self._lock:
            return self._state

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def add_listener(self, callback: StateListener) -> None:
        """Register a callback for state transition notifications."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: StateListener) -> None:
        """Remove a registered callback."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify(self, old_state: AssistantState, new_state: AssistantState, message: Optional[str] = None) -> None:
        for cb in list(self._listeners):
            try:
                cb(old_state, new_state, message)
            except Exception as exc:
                logger.debug("State listener callback error: %s", exc)

    def transition_to(self, new_state: AssistantState, message: Optional[str] = None, force: bool = False) -> None:
        """Transition to a new state safely under lock.

        Args:
            new_state: Destination AssistantState.
            message: Optional status or diagnostic detail.
            force: If True, bypasses serialization busy checks (used for cancel/error).
        """
        with self._lock:
            old_state = self._state
            if old_state == new_state:
                return

            # Check busy serialization
            busy_states = (AssistantState.LISTENING, AssistantState.TRANSCRIBING, AssistantState.EXECUTING)
            if not force and old_state in busy_states and new_state in busy_states:
                raise StateTransitionError(
                    f"Cannot transition to {new_state.value}: Assistant is currently busy ({old_state.value})."
                )

            if new_state in (AssistantState.IDLE, AssistantState.CANCELLED, AssistantState.ERROR):
                if new_state == AssistantState.IDLE:
                    self._cancel_event.clear()
                    self._active_plan = None

            self._state = new_state
            logger.info("Assistant state: %s -> %s%s", old_state.value, new_state.value, f" ({message})" if message else "")

        self._notify(old_state, new_state, message)

    def request_cancel(self, reason: str = "User requested stop") -> None:
        """Signal immediate cancellation to any running background task."""
        with self._lock:
            self._cancel_event.set()
            old_state = self._state
            self._state = AssistantState.CANCELLED
            logger.info("Cancellation requested (%s). State forced to CANCELLED.", reason)

        self._notify(old_state, AssistantState.CANCELLED, reason)

    def reset(self) -> None:
        """Reset state machine to clean IDLE state."""
        self.transition_to(AssistantState.IDLE, message="Reset to idle", force=True)

    def set_active_plan(self, plan: Optional[ActionPlan]) -> None:
        """Assign currently executing or pending action plan."""
        with self._lock:
            self._active_plan = plan

    def get_active_plan(self) -> Optional[ActionPlan]:
        with self._lock:
            return self._active_plan
