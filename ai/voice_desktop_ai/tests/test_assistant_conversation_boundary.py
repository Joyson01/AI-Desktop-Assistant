import assistant


CONVERSATION_INPUTS = [
    "Maruti hello",
    "hello Maruti",
    "Maruti India ke Prime Minister kaun hain?",
    "Maruti aaj ki news kya hai?",
    "Maruti mujhe Hindi mein samjhao",
]


class FakeConversationProvider:
    def __init__(self):
        self.calls = []

    def answer(self, prompt, route=None):
        self.calls.append({"prompt": prompt, "route": route})
        return "FAKE_CONVERSATION_RESPONSE"


class FakeConfig:
    api_key = ""
    model = "grok-test"
    configured = False


def make_assistant(monkeypatch, provider):
    spoken = []
    monkeypatch.setattr(assistant, "speak", spoken.append)
    monkeypatch.setattr(assistant, "load_provider_config", lambda: FakeConfig())
    monkeypatch.delenv("MARUTI_GROK_LIVE", raising=False)
    monkeypatch.setattr(
        assistant,
        "GrokVisualBrain",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("Grok must not initialize")),
    )
    instance = assistant.AccessibilityAssistant(
        dry_run=True,
        conversation_provider=provider,
    )
    instance.observe = lambda *args, **kwargs: None
    return instance, spoken


def test_conversation_inputs_cross_actual_assistant_boundary_without_grok(monkeypatch):
    provider = FakeConversationProvider()
    instance, spoken = make_assistant(monkeypatch, provider)

    for transcript in CONVERSATION_INPUTS:
        assert instance.handle(transcript) is True

    assert spoken == [
        "Hello! How can I help you today?",
        "Hello! How can I help you today?",
        "FAKE_CONVERSATION_RESPONSE",
        "FAKE_CONVERSATION_RESPONSE",
        "FAKE_CONVERSATION_RESPONSE",
    ]
    assert [call["prompt"] for call in provider.calls] == CONVERSATION_INPUTS[2:]
    assert all(call["route"].route == "conversation" for call in provider.calls)


def test_computer_inputs_do_not_call_conversation_provider_or_grok(monkeypatch):
    provider = FakeConversationProvider()
    instance, spoken = make_assistant(monkeypatch, provider)
    executed = []
    instance.execute_step = lambda intent: executed.append(intent.action) or True

    for transcript in ("Maruti Chrome kholo", "Maruti scroll down karo"):
        assert instance.handle(transcript) is True

    assert provider.calls == []
    assert executed == ["open", "scroll_down"]
    assert spoken == ["Okay, done.", "Okay, done."]