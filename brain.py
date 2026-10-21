"""Conversation brain: Gemini REST API with Google Search grounding for live facts."""
import logging

from config import GEMINI_API_KEY, GEMINI_MODEL

log = logging.getLogger("maruti.brain")
SYSTEM = ("You are Maruti, a friendly voice assistant. Answer in one or two short spoken sentences, "
          "no markdown. Reply in the same language the user used (English, Hindi or Hinglish).")


class Brain:
    def __init__(self):
        self.history = []  # last few turns for multi-turn context

    def ask(self, question: str) -> str:
        if not GEMINI_API_KEY:
            return "I need a Gemini API key to answer general questions. Please add it to the dot env file."
        import requests
        self.history.append({"role": "user", "parts": [{"text": question}]})
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM}]},
            "contents": self.history[-8:],
            "tools": [{"google_search": {}}],  # grounding: current PM, CEO, news ...
        }
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json=payload, timeout=25)
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            answer = " ".join(p.get("text", "") for p in parts).strip() or "I could not find an answer."
        except Exception as exc:  # network, quota, bad key ...
            log.warning("Gemini failed: %s", exc)
            self.history.pop()
            return "Sorry, I could not reach the AI service right now."
        self.history.append({"role": "model", "parts": [{"text": answer}]})
        return answer
