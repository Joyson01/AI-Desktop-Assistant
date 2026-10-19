from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brain.intent_router import IntentRouter, CONVERSATION, COMPUTER_ACTION, WEB_NAVIGATION, SYSTEM_CONTROL, MIXED, AMBIGUOUS


@dataclass
class BrainDecision:
    mode: str
    goal: str
    confidence: float = 0.0
    action: str | None = None
    query: str | None = None
    url: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    response: str | None = None
    needs_confirmation: bool = False


class SmartBrain:
    """
    Modular routing layer that classifies and routes user commands.
    Uses existing IntentRouter as the source of truth for high-level classification,
    then applies additional logic to further classify computer actions.
    """

    # Fast local commands that don't need AI/visual processing
    FAST_LOCAL_KEYWORDS = {
        "scroll", "scroll down", "scroll up", "down", "up",
        "press", "enter", "escape", "tab", "backspace",
        "volume", "mute", "unmute", "pause",
        "back", "forward", "home", "top", "end", "bottom",
        "refresh", "reload", "ctrl+r", "next window",
    }

    # Media/music/video keywords
    MEDIA_KEYWORDS = {
        "song", "music", "gaana", "gana", "play", "chalao",
        "video", "episode", "youtube", "movie",
    }

    # Website/navigation keywords
    NAVIGATION_KEYWORDS = {
        "chrome", "youtube", "google", "website", "kholo", "open",
    }

    def __init__(self, router, conversation=None):
        """
        Initialize SmartBrain.
        
        Args:
            router: IntentRouter instance
            conversation: ConversationManager (optional)
        """
        self.router = router
        self.conversation = conversation
        self._pending_route = None

    def use_route(self, route):
        """Reuse a route already computed by the caller once."""
        self._pending_route = route

    def decide(self, transcript: str, memory=None, route=None) -> BrainDecision:
        """
        Make a routing decision for a transcript.
        
        Args:
            transcript: User's voice command
            memory: Optional Memory instance for context
            
        Returns:
            BrainDecision with routing mode and metadata
        """
        if not transcript or not isinstance(transcript, str):
            return BrainDecision(
                mode="ambiguous",
                goal=transcript or "",
                confidence=0.0,
            )

        goal = transcript.strip()
        text_lower = goal.lower()
        
        # Pre-routing: Check for web navigation first (takes priority)
        route = route or self._pending_route or self.router.route(transcript)
        self._pending_route = None
        if route.route == WEB_NAVIGATION:
            return BrainDecision(
                mode="web_navigation",
                goal=goal,
                confidence=0.9,
                query=route.metadata.get("target"),
            )
        
        # Pre-routing: Check for media commands
        if self._is_media_command(text_lower):
            query = self._extract_media_query(transcript, text_lower)
            return BrainDecision(
                mode="web_media",
                goal=goal,
                confidence=0.85,
                query=query,
            )
        
        # Route based on intent_router's classification
        if route.route == CONVERSATION:
            return BrainDecision(
                mode="conversation",
                goal=goal,
                confidence=route.confidence,
                response=route.conversation_text,
            )

        if route.route == MIXED:
            return BrainDecision(
                mode="mixed",
                goal=goal,
                confidence=route.confidence,
                needs_confirmation=True,
                response=route.clarification,
            )

        if route.route == AMBIGUOUS:
            return BrainDecision(
                mode="ambiguous",
                goal=goal,
                confidence=0.0,
                response=route.clarification,
            )

        if route.route == SYSTEM_CONTROL:
            metadata = route.metadata or {}
            return BrainDecision(
                mode="system_control",
                goal=goal,
                confidence=route.confidence,
                action=metadata.get("system_action"),
                response=metadata.get("goal", goal),
            )

        if route.route == COMPUTER_ACTION:
            # Classify computer actions further
            return self._classify_computer_action(transcript, goal, route)

        # Fallback
        return BrainDecision(
            mode="ambiguous",
            goal=goal,
            confidence=0.0,
        )

    def _classify_computer_action(self, transcript: str, goal: str, route) -> BrainDecision:
        """
        Classify computer action routes into more specific paths.
        
        Returns one of:
        - fast_local: Simple keyboard/mouse operations
        - web_media: Music/video commands
        - web_navigation: Website/URL opening
        - computer_visual: Visual tasks requiring screenshot analysis
        """
        text_lower = goal.lower()

        # Check for fast local operations
        if self._is_fast_local(text_lower):
            return BrainDecision(
                mode="fast_local",
                goal=goal,
                confidence=0.95,
                action=route.semantic_intent,
            )

        # Check for media/music/video commands
        if self._is_media_command(text_lower):
            query = self._extract_media_query(transcript, text_lower)
            return BrainDecision(
                mode="web_media",
                goal=goal,
                confidence=0.85,
                query=query,
            )

        # Default: visual-based computer action
        return BrainDecision(
            mode="computer_visual",
            goal=goal,
            confidence=route.confidence,
            action=route.semantic_intent,
        )

    def _is_fast_local(self, text: str) -> bool:
        """Check if command is a fast local operation."""
        return any(kw in text for kw in self.FAST_LOCAL_KEYWORDS)

    def _is_media_command(self, text: str) -> bool:
        """Check if command is media/music/video related."""
        return any(kw in text for kw in self.MEDIA_KEYWORDS)

    def _is_web_navigation(self, text: str) -> bool:
        """Check if command is website navigation."""
        # Simple pattern: "kholo", "open" combined with browser/site names
        return self.router.route(text).route == WEB_NAVIGATION

    def _extract_media_query(self, transcript: str, text_lower: str) -> str:
        """Extract search query from media command."""
        # Remove media keywords to get the query
        keywords_to_remove = {
            "youtube", "song", "music", "video", "play", "movie",
            "chalao", "chala", "do", "karo", "kholo", "pe", "par",
        }
        contextual_words = {"this", "that", "it", "same", "one", "wahi", "yeh", "woh"}

        words = text_lower.split()
        query_words = [
            w for w in words
            if w not in keywords_to_remove and w not in contextual_words and len(w) > 1
        ]

        query = " ".join(query_words).strip()
        return query
