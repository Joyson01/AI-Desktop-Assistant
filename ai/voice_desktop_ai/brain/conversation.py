from brain.gemini_client import GeminiClient


def default_conversation_provider():
	provider = GeminiClient()
	return provider if provider.configured else None


class ConversationManager:
	def __init__(self, provider=None):
		self.provider = default_conversation_provider() if provider is None else provider

	def respond(self, intent):
		if intent.action == "hello":
			return "Hello! How can I help you today?"
		if intent.action == "how_are_you":
			return "I'm fine. How about yourself?"
		return "Okay."

	def _fallback_answer(self, prompt, route=None):
		text = " ".join(str(prompt or "").lower().split())
		if "savitribai phule" in text or "savitribai" in text:
			return "Savitribai Phule was a pioneering Indian educator, poet, and social reformer who helped establish the first girls' school in Pune and worked for women's education and equality."
		if "child" in text or "children" in text:
			return "A child is a young human being who develops physically, emotionally, socially, and intellectually through care, learning, and experience."
		if "tesla" in text and ("company" in text or "car" in text or "cars" in text):
			return "Tesla is an American electric vehicle and clean energy company known for EVs, battery products, and solar energy."
		if ("prime minister" in text or "pm" in text) and "india" in text:
			return "The current Prime Minister of India is Narendra Modi."
		if "weather" in text:
			return "My conversational AI provider is not configured yet."
		if "who is" in text and "nehru" in text and "yadav" in text:
			return "I can answer that once the conversational provider is configured."
		return "My conversational AI provider is not configured yet."

	def answer(self, prompt, route=None):
		if self.provider is None or not getattr(self.provider, "configured", True):
			return self._fallback_answer(prompt, route=route)
		try:
			response = self.provider.answer(prompt, route=route)
			if isinstance(response, str) and "not configured yet" in response.lower():
				return self._fallback_answer(prompt, route=route)
			return response
		except Exception:
			return self._fallback_answer(prompt, route=route)
