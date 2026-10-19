from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from typing import Any


@dataclass
class Memory:
    max_history: int = 20
    history: deque = field(default_factory=lambda: deque(maxlen=20))

    current_app: str | None = None
    current_window: str | None = None
    current_url: str | None = None

    last_goal: str | None = None
    last_query: str | None = None
    last_target: Any = None
    last_result: Any = None

    preferences: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Ensure deque respects max_history
        if self.history.maxlen != self.max_history:
            old_history = list(self.history)
            self.history = deque(old_history, maxlen=self.max_history)

    def remember_turn(self, user: str, assistant: str):
        self.history.append({
            "user": user,
            "assistant": assistant,
        })

    def remember_goal(self, goal: str):
        self.last_goal = goal

    def remember_query(self, query: str):
        self.last_query = query

    def remember_target(self, target: Any):
        self.last_target = target

    def remember_result(self, result: Any):
        self.last_result = result

    def set_screen(self, state):
        self.current_app = getattr(state, "active_application", None)
        self.current_window = getattr(state, "active_window", None)

    def context(self) -> dict:
        return {
            "current_app": self.current_app,
            "current_window": self.current_window,
            "current_url": self.current_url,
            "last_goal": self.last_goal,
            "last_query": self.last_query,
            "last_target": self.last_target,
            "last_result": self.last_result,
            "preferences": self.preferences,
            "recent_history": list(self.history)[-8:],
        }
