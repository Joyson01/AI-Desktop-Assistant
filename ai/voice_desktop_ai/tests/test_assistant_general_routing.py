from types import SimpleNamespace

import assistant
from brain.intent import Intent


class FakeConfig:
    api_key = "test-key"
    model = "grok-test"
    configured = True


class FakeConversationProvider:
    def __init__(self):
        self.calls = []

    def answer(self, prompt, route=None):
        self.calls.append({"prompt": prompt, "route": route})
        return f"provider answer: {prompt}"


def make_assistant(monkeypatch, provider=None, grok_live=False):
    spoken = []
    monkeypatch.setattr(assistant, "speak", spoken.append)
    monkeypatch.setattr(assistant, "load_provider_config", lambda: FakeConfig())
    if grok_live:
        monkeypatch.setenv("MARUTI_GROK_LIVE", "1")
    else:
        monkeypatch.delenv("MARUTI_GROK_LIVE", raising=False)
    instance = assistant.AccessibilityAssistant(dry_run=True, conversation_provider=provider)
    instance.observe = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("observe should not run"))
    return instance, spoken


def test_english_hindi_and_hinglish_questions_use_conversation_provider(monkeypatch):
    provider = FakeConversationProvider()
    instance, spoken = make_assistant(monkeypatch, provider=provider)

    assert instance.handle("Maruti who is the prime minister of India") is True
    assert instance.handle("Maruti भारत के प्रधानमंत्री कौन हैं") is True
    assert instance.handle("Maruti Prime Minister kaun hai") is True

    assert spoken == [
        "provider answer: Maruti who is the prime minister of India",
        "provider answer: Maruti भारत के प्रधानमंत्री कौन हैं",
        "provider answer: Maruti Prime Minister kaun hai",
    ]
    assert [call["route"].route for call in provider.calls] == ["conversation"] * 3


def test_maruti_greetings_are_conversation_without_provider_call(monkeypatch):
    provider = FakeConversationProvider()
    instance, spoken = make_assistant(monkeypatch, provider=provider)

    assert instance.handle("Maruti hello") is True
    assert instance.handle("hello Maruti") is True

    assert spoken == [
        "Hello! How can I help you today?",
        "Hello! How can I help you today?",
    ]
    assert provider.calls == []


def test_provider_unavailable_message_is_not_treated_as_computer_action(monkeypatch):
    instance, spoken = make_assistant(monkeypatch)

    assert instance.handle("Aaj ki news batao") is True

    assert spoken == []


def test_tesla_company_request_has_short_local_fallback_without_provider(monkeypatch):
    instance, spoken = make_assistant(monkeypatch)

    assert instance.handle("about of tesla company") is True

    assert spoken == []


def test_computer_commands_do_not_require_maruti_or_call_conversation_provider(monkeypatch):
    provider = FakeConversationProvider()
    instance, spoken = make_assistant(monkeypatch, provider=provider)
    state = SimpleNamespace(ui_elements=[], screenshot=None, visual_candidates=[])
    instance.state = state
    instance.observe = lambda *args, **kwargs: state
    executed = []
    structured = []
    instance.execute_step = lambda intent: executed.append(intent.action) or True
    instance._execute_structured = lambda action: structured.append(action) or True

    for transcript, action in (
        ("open Chrome", "open"),
        ("click on money", "click"),
        ("scroll down", "scroll_down"),
        ("press ctrl+r", "hotkey"),
    ):
        assert instance.handle(transcript) is True
        if action == "hotkey":
            assert structured[-1] == {"action": "hotkey", "keys": ["ctrl", "r"]}
        else:
            assert executed[-1] == action

    assert provider.calls == []
    assert spoken == ["Okay, done."] * 4


def test_unaddressed_information_and_incomplete_speech_do_not_call_provider(monkeypatch):
    provider = FakeConversationProvider()
    instance, spoken = make_assistant(monkeypatch, provider=provider)

    for transcript in ("best", "Tesla", "what is this", "weather", "hello"):
        assert instance.handle(transcript) is True

    assert provider.calls == []
    assert spoken == []


def test_maruti_addressed_information_is_sent_to_provider(monkeypatch):
    provider = FakeConversationProvider()
    instance, spoken = make_assistant(monkeypatch, provider=provider)

    assert instance.handle("Maruti tell me about Tesla") is True

    assert [call["prompt"] for call in provider.calls] == ["Maruti tell me about Tesla"]
    assert spoken == ["provider answer: Maruti tell me about Tesla"]


def test_maruti_anywhere_in_information_sentence_is_sent_unchanged(monkeypatch):
    provider = FakeConversationProvider()
    instance, spoken = make_assistant(monkeypatch, provider=provider)

    for transcript in (
        "Maruti right explain Python",
        "tell me Maruti who is PM of India",
        "hey Maruti what is AI",
    ):
        assert instance.handle(transcript) is True

    assert [call["prompt"] for call in provider.calls] == [
        "Maruti right explain Python",
        "tell me Maruti who is PM of India",
        "hey Maruti what is AI",
    ]
    assert spoken == [f"provider answer: {prompt}" for prompt in [
        "Maruti right explain Python",
        "tell me Maruti who is PM of India",
        "hey Maruti what is AI",
    ]]


def test_ctrl_c_stops_run_and_clears_pending_confirmation(monkeypatch):
    instance, _ = make_assistant(monkeypatch)
    instance.pending_confirmation = "close_window"
    instance.observe = lambda *args, **kwargs: None

    class InterruptingSpeech:
        def listen(self):
            raise KeyboardInterrupt

    instance.speech = InterruptingSpeech()

    instance.run()

    assert instance.pending_confirmation is None


def test_isolated_topics_are_ignored_without_provider_call(monkeypatch):
    provider = FakeConversationProvider()
    instance, spoken = make_assistant(monkeypatch, provider=provider)

    assert instance.handle("nehru yadav") is True
    assert instance.handle("tesla") is True
    assert instance.handle("lassi") is True

    assert spoken == []
    assert provider.calls == []


def test_acknowledgement_phrases_are_silent(monkeypatch):
    provider = FakeConversationProvider()
    instance, spoken = make_assistant(monkeypatch, provider=provider)

    assert instance.handle("okay i understand") is True
    assert instance.handle("I understand") is True

    assert spoken == []
    assert provider.calls == []


def test_computer_action_routes_to_visual_orchestrator_when_enabled(monkeypatch):
    handled = []
    monkeypatch.setattr(assistant.AccessibilityAssistant, "_handle_grok", lambda self, goal: handled.append(goal) or True)
    instance, spoken = make_assistant(monkeypatch, grok_live=True)

    assert instance.handle("Chrome kholo") is True
    assert instance.handle("YouTube kholo aur Saiyaara search karo") is True

    assert handled == ["Chrome kholo", "YouTube kholo aur Saiyaara search karo"]
    assert spoken == []


def test_ambiguous_and_mixed_routes_ask_for_clarification_without_observing(monkeypatch):
    instance, spoken = make_assistant(monkeypatch)

    assert instance.handle("Chrome") is True
    assert instance.handle("Chrome kholo aur phir mujhe batao Prime Minister kaun hai.") is True

    assert "not sure" in spoken[0]
    assert "both a computer action and a question" in spoken[1]


def test_shutdown_requires_yes_confirmation_before_execution(monkeypatch):
    instance, spoken = make_assistant(monkeypatch)
    executed = []
    instance.execute_step = lambda intent: executed.append(intent.action) or True

    assert instance.handle("Shut down") is True
    assert executed == []
    assert spoken == ["Are you sure you want to shut down the computer?"]

    for response in ("Yes", "Haan", "Han", "हाँ", "हां"):
        instance, _ = make_assistant(monkeypatch)
        executed = []
        instance.execute_step = lambda intent: executed.append(intent.action) or True

        assert instance.handle("Shut down") is True
        assert instance.handle(response) is True
        assert executed == ["shutdown"]


def test_shutdown_is_cancelled_by_no_or_unclear_confirmation(monkeypatch):
    for response in ("No", "maybe"):
        instance, spoken = make_assistant(monkeypatch)
        executed = []
        instance.execute_step = lambda intent: executed.append(intent.action) or True

        assert instance.handle("Shut down") is True
        assert instance.handle(response) is True

        assert executed == []
        assert spoken == [
            "Are you sure you want to shut down the computer?",
            "Shutdown cancelled.",
        ]


def test_close_window_requires_confirmation_then_executes_close_action(monkeypatch):
    instance, spoken = make_assistant(monkeypatch)
    executed = []
    instance._execute_structured = lambda action: executed.append(action) or True

    assert instance.handle("close the window") is True
    assert executed == []
    assert spoken == ["Are you sure you want to close the current window?"]

    assert instance.handle("yes") is True
    assert executed == [{"action": "hotkey", "keys": ["alt", "f4"]}]


def test_click_reuses_current_screen_and_pre_resolves_target(monkeypatch):
    instance, _ = make_assistant(monkeypatch)
    observations = []
    state = SimpleNamespace(ui_elements=[], screenshot=object(), visual_candidates=[])
    instance.state = state
    instance.dry_run = False

    def observe(*, include_fallback=False):
        observations.append(include_fallback)
        instance.state = state
        return state

    def fake_execute(intent, before, refresh, resolve, invoke, dry_run=False, resolved_element=None):
        assert before is state
        assert resolved_element is None
        return SimpleNamespace(success=True, verified=True, message="clicked")

    instance.observe = observe
    monkeypatch.setattr(assistant, "execute", fake_execute)

    assert instance.execute_step(Intent("click", target="File")) is True
    assert observations == []
