import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass


class GeminiClient:
    """Optional Google GenAI boundary; the local assistant works without it."""

    def __init__(self, api_key=None, model=None):
        self.api_key = str(api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.client = None
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except (ImportError, Exception):
                self.client = None

    @property
    def configured(self):
        return self.client is not None

    def analyze(self, prompt, screenshot=None, context=None):
        if not self.configured:
            return {"action": "ask_user", "message": "Gemini brain is not configured."}
        contents = [prompt]
        if context:
            contents.append(json.dumps(context, ensure_ascii=False))
        if screenshot is not None:
            contents.append(screenshot)
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config={"response_mime_type": "application/json"},
        )
        return json.loads(response.text)

    def answer(self, prompt, route=None):
        if not self.configured:
            return "My conversational AI provider is not configured yet."
        chats = getattr(self.client, "chats", None)
        if chats is not None and callable(getattr(chats, "create", None)):
            chat = chats.create(model=self.model)
            response = chat.send_message(prompt)
        else:
            response = self.client.models.generate_content(model=self.model, contents=prompt)
        return response.text
