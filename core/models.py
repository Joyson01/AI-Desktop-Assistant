"""Typed command, action, capability, and execution models for MARUTI.

Provides immutable and dataclass representations for:
- Speech transcripts with confidence and language metadata.
- Parsed intents with confidence, parameters, and ambiguity rating.
- Action plans with risk tier and confirmation requirements.
- Desktop execution contexts, backend capabilities, and evidence verification levels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import enum
import time
from typing import Any, Dict, List, Optional


class ActionRisk(enum.Enum):
    """Risk tier for desktop actions."""
    SAFE = "safe"              # Reversible, safe to execute automatically
    SENSITIVE = "sensitive"    # Consequential, requires explicit human confirmation
    BLOCKED = "blocked"        # Prohibited by security policy or missing capability


class VerificationLevel(enum.Enum):
    """Evidence levels for action verification."""
    PLANNED = "planned"
    ISSUED = "issued"
    FOCUS_VERIFIED = "focus_verified"
    TARGET_FOUND = "target_found"
    POSTCONDITION_VERIFIED = "postcondition_verified"
    UNVERIFIABLE = "unverifiable"
    BLOCKED = "blocked"
    FAILED = "failed"


class AssistantState(enum.Enum):
    """Central state machine stages for MARUTI."""
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    REVIEW = "review"
    ROUTING = "routing"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass(frozen=True)
class Transcript:
    """Raw and normalized speech transcript."""
    raw_text: str
    normalized_text: str
    confidence: float = 1.0
    language: str = "en-IN"
    is_final: bool = True
    timestamp: float = field(default_factory=time.time)


@dataclass
class ParsedIntent:
    """NLU router output with typed attributes."""
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    raw: str = ""
    is_ambiguous: bool = False
    clarification_prompt: Optional[str] = None


@dataclass
class ActionStep:
    """Single atomic desktop or system step within a plan."""
    action_name: str
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    risk: ActionRisk = ActionRisk.SAFE


@dataclass
class ActionPlan:
    """Structured plan ready for confirmation and execution."""
    intent: ParsedIntent
    steps: List[ActionStep] = field(default_factory=list)
    risk: ActionRisk = ActionRisk.SAFE
    confirmation_prompt: Optional[str] = None
    target_app: Optional[str] = None
    requires_focus: bool = False
    dry_run: bool = False
    created_at: float = field(default_factory=time.time)


@dataclass
class VerificationResult:
    """Evidence and outcome details for an executed step."""
    level: VerificationLevel
    success: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Standardized result returned by Assistant for every operation."""
    success: bool
    message: str
    intent_name: str
    plan: Optional[ActionPlan] = None
    verification: Optional[VerificationResult] = None
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def __str__(self) -> str:
        return self.message


@dataclass
class BackendCapability:
    """Runtime environmental capabilities detected on host desktop."""
    os_name: str
    session_type: str  # 'x11', 'wayland', 'windows', 'headless'
    has_display: bool
    has_microphone: bool
    has_pyaudio: bool
    has_tesseract: bool
    has_native_clipboard: bool
    supports_synthetic_keys: bool
    supports_window_focus_check: bool
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionContext:
    """Current active desktop target context before issuing an action."""
    target_app: Optional[str] = None
    active_window_title: Optional[str] = None
    focus_confirmed: bool = False
    active_url: Optional[str] = None
    active_site: Optional[str] = None
    backend: Optional[BackendCapability] = None
