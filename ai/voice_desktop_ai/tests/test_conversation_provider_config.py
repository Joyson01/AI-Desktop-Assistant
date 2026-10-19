import assistant
from brain.conversation import ConversationManager, default_conversation_provider


class FakeGemini:
    def __init__(self, configured):
        self.configured = configured


class FakeGeminiResponse:
    text = "The current prime minister is Narendra Modi."


class FakeGeminiModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return FakeGeminiResponse()


class FakeConfiguredGemini:
    def __init__(self):
        self.model = "gemini-test"
        self.client = type("Client", (), {"models": FakeGeminiModels()})()

    @property
    def configured(self):
        return True

    def answer(self, prompt, route=None):
        response = self.client.models.generate_content(model=self.model, contents=prompt)
        return response.text


def test_default_conversation_provider_uses_gemini_client_configuration(monkeypatch):
    monkeypatch.setattr("brain.conversation.GeminiClient", lambda: FakeGemini(True))

    provider = default_conversation_provider()

    assert isinstance(provider, FakeGemini)


def test_default_conversation_provider_is_none_when_gemini_is_unavailable(monkeypatch):
    monkeypatch.setattr("brain.conversation.GeminiClient", lambda: FakeGemini(False))

    assert default_conversation_provider() is None


def test_gemini_conversation_uses_plain_text_generation(monkeypatch):
    from brain.gemini_client import GeminiClient

    client = GeminiClient.__new__(GeminiClient)
    client.api_key = "test-only-key"
    client.model = "gemini-test"
    client.client = type("Client", (), {"models": FakeGeminiModels()})()

    assert client.answer("who is the prime minister of india") == "The current prime minister is Narendra Modi."
    assert client.client.models.calls == [{
        "model": "gemini-test",
        "contents": "who is the prime minister of india",
    }]


def test_assistant_uses_default_conversation_provider_only_when_not_injected(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(assistant, "default_conversation_provider", lambda: sentinel)
    monkeypatch.setattr(assistant, "load_provider_config", lambda: type("Config", (), {"configured": False})())
    instance = assistant.AccessibilityAssistant(dry_run=True)

    assert instance.conversation.provider is sentinel


def test_explicit_conversation_provider_remains_authoritative(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(assistant, "default_conversation_provider", lambda: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(assistant, "load_provider_config", lambda: type("Config", (), {"configured": False})())
    instance = assistant.AccessibilityAssistant(dry_run=True, conversation_provider=sentinel)

    assert instance.conversation.provider is sentinel


def test_conversation_manager_reports_clear_missing_provider_message():
    assert ConversationManager().answer("what is today weather") == "My conversational AI provider is not configured yet."


def test_conversation_manager_has_local_fallback_for_savitribai_phule():
    answer = ConversationManager(provider=FakeGemini(False)).answer("tell me something about Savitribai Phule")

    assert "educator" in answer.lower()
    assert "women" in answer.lower()


def test_conversation_manager_has_local_fallback_for_child():
    answer = ConversationManager(provider=FakeGemini(False)).answer("tell me something about child")

    assert "young human" in answer.lower()
    assert "develops" in answer.lower()