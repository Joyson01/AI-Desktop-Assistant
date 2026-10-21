"""NLU router module — re-exports the IntentRouter from the project root.

This module exists so main.py can use the preferred import path
``from nlu.router import IntentRouter`` while the legacy path
``from intent_router import IntentRouter`` continues to work as a fallback.
"""
from intent_router import Intent, IntentRouter  # noqa: F401

__all__ = ["IntentRouter", "Intent"]
