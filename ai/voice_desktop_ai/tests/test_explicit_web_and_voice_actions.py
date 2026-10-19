from brain.intent_router import AMBIGUOUS, COMPUTER_ACTION, WEB_NAVIGATION, IntentRouter
from brain.smart_brain import SmartBrain
from brain.web_resolver import OfficialSiteResult, SearchResult, WebResolver
from computer.action_executor import ActionExecutor
from computer.actions import ActionValidator


router = IntentRouter()


def test_only_explicit_web_phrases_route_to_web_navigation():
    explicit = [
        "open web unacademy",
        "open website unacademy",
        "open the website of unacademy",
        "website unacademy",
        "maruti open web google docs",
        "open web Gmail",
        "open web Google Maps",
        "open web Google Docs",
        "open web google do",
        "open web Google Sheets",
        "open web WhatsApp",
        "open web UIDAI",
        "open web Physics Wallah",
        "open my physics wala",
        "web open Gmail",
        "web kholo Gmail",
        "web par Gmail kholo",
        "website open Gmail",
        "open website Gmail",
    ]
    for text in explicit:
        result = router.route(text)
        assert result.route == WEB_NAVIGATION, text
        assert result.metadata["target"]


def test_open_web_without_target_is_explicit_web_intent():
    result = router.route("open web")
    assert result.route == WEB_NAVIGATION
    assert result.metadata["target"] == ""
    assert router.route("open the website of").metadata["target"] == ""


def test_bare_or_ambiguous_site_names_do_not_open_websites():
    for text in ("Gmail", "open Gmail", "Google Maps", "open", "open this"):
        assert router.route(text).route != WEB_NAVIGATION
        assert SmartBrain(router).decide(text).mode != "web_navigation"


def test_local_and_contextual_commands_route_without_real_execution():
    cases = {
        "open wordpad": COMPUTER_ACTION,
        "open file explorer": COMPUTER_ACTION,
        "take screenshot": COMPUTER_ACTION,
        "mouse right": COMPUTER_ACTION,
        "mouse down": COMPUTER_ACTION,
        "left button down": COMPUTER_ACTION,
        "left button up": COMPUTER_ACTION,
        "press control + a": COMPUTER_ACTION,
    }
    for text, expected_route in cases.items():
        assert router.route(text).route == expected_route

    decision = SmartBrain(router).decide("play this song")
    assert decision.mode == "web_media"
    assert decision.query == ""


def test_canonical_screenshot_and_mouse_actions_validate():
    actions = [
        {"action": "screenshot_start"},
        {"action": "mouse_move", "direction": "right", "amount": 200},
        {"action": "mouse_down", "button": "left"},
        {"action": "mouse_up", "button": "left"},
    ]
    assert all(ActionValidator.validate(action)[0] for action in actions)


def test_mouse_execution_is_fakeable(monkeypatch):
    calls = []
    monkeypatch.setattr("computer.action_executor.pyautogui.moveRel", lambda *args, **kwargs: calls.append(("move", args, kwargs)))
    monkeypatch.setattr("computer.action_executor.pyautogui.mouseDown", lambda **kwargs: calls.append(("down", kwargs)))
    monkeypatch.setattr("computer.action_executor.pyautogui.mouseUp", lambda **kwargs: calls.append(("up", kwargs)))

    executor = ActionExecutor()
    assert executor.execute({"action": "mouse_move", "direction": "right", "amount": 200})["success"]
    assert executor.execute({"action": "mouse_down", "button": "left"})["success"]
    assert executor.execute({"action": "mouse_up", "button": "left"})["success"]
    assert calls[0][1][:2] == (200, 0)


def test_website_resolution_ranks_official_candidate_without_opening_it(monkeypatch):
    resolver = WebResolver()
    monkeypatch.setattr(
        resolver,
        "_search_official_candidates",
        lambda target: [
            ("Gmail official", "https://mail.google.com/", 0.85),
            ("Gmail clone", "https://example.invalid/", 0.5),
        ],
    )
    result = resolver.resolve_website("Gmail")
    assert isinstance(result, SearchResult)
    assert result.url == "https://mail.google.com/"


def test_known_sites_resolve_without_ai_or_network():
    resolver = WebResolver()
    for target, expected in {
        "gmail": "https://mail.google.com/",
        "google maps": "https://maps.google.com/",
        "google docs": "https://docs.google.com/",
        "google do": "https://docs.google.com/",
        "physics wala": "https://www.pw.live/",
        "pw": "https://www.pw.live/",
        "unacademy": "https://unacademy.com/",
        "udiai": "https://uidai.gov.in/",
        "whatsapp": "https://web.whatsapp.com/",
        "chrome": "https://www.google.com/chrome/",
        "youtube": "https://www.youtube.com/",
    }.items():
        result = resolver.resolve_website(target)
        assert result is not None, target
        assert result.url == expected, (target, result.url if result else None)


class FakeProvider:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.configured = True
        self.calls = []

    def resolve_website(self, prompt):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        return self.response

    def analyze(self, prompt):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        return self.response


class ChatUrlProvider:
    configured = True

    def __init__(self, response):
        self.response = response
        self.calls = []

    def answer(self, prompt):
        self.calls.append(prompt)
        return self.response


def official_payload(url, domain, confidence=0.99):
    return {
        "name": "Instagram",
        "official_url": url,
        "official_domain": domain,
        "confidence": confidence,
        "reason": "Official website",
    }


def test_gemini_is_used_when_grok_fails():
    grok = FakeProvider(error=TimeoutError("grok unavailable"))
    gemini = FakeProvider(response=official_payload("https://www.instagram.com/", "instagram.com"))
    result = WebResolver(grok=grok, gemini=gemini).resolve_website("instagram")
    assert result.url == "https://www.instagram.com/"
    assert grok.calls and gemini.calls
    assert result.resolver == "gemini"


def test_gemini_chat_response_extracts_official_url_for_arbitrary_targets():
    targets = {
        "Google Docs": "https://docs.google.com/",
        "Google Maps": "https://maps.google.com/",
        "HP website": "https://www.hp.com/",
        "PW": "https://www.pw.live/",
        "Unacademy": "https://unacademy.com/",
    }
    provider = ChatUrlProvider("")
    resolver = WebResolver(gemini=provider)

    for target, url in targets.items():
        provider.response = f"The official website is {url}."
        result = resolver.resolve_website(target)
        assert result is not None, target
        assert result.url == url

    assert len(provider.calls) == len(targets)


def test_dynamic_provider_resolution_is_used_for_unknown_targets():
    provider = ChatUrlProvider("Official site: https://www.whatsapp.com/")

    result = WebResolver(gemini=provider).resolve_website("WhatsApp")

    assert result is not None
    assert result.url == "https://www.whatsapp.com/"
    assert provider.calls


def test_dynamic_gemini_resolution_works_without_local_catalog():
    provider = ChatUrlProvider("The official website is https://example.com/.")

    result = WebResolver(gemini=provider).resolve_website("Example Company")

    assert result is not None
    assert result.url == "https://example.com/"
    assert result.resolver == "gemini"


def test_firefox_resolves_dynamically_to_mozilla_without_local_mapping():
    provider = ChatUrlProvider("https://www.mozilla.org/firefox/")

    result = WebResolver(gemini=provider).resolve_website("firefox")

    assert result is not None
    assert result.url == "https://www.mozilla.org/firefox/"
    assert result.resolver == "gemini"


def test_generic_search_fallback_prefers_exact_official_root_domain(monkeypatch):
    resolver = WebResolver()
    monkeypatch.setattr(
        resolver,
        "_search_official_candidates",
        lambda target: [
            ("Flipkart login", "https://www.flipkart.com/account/login", 0.7),
            ("Flipkart official", "https://www.flipkart.com/", 0.9),
        ],
    )

    result = resolver.resolve_website("flipkart")

    assert result is not None
    assert result.url == "https://www.flipkart.com/"


def test_grok_is_used_when_gemini_returns_an_invalid_search_url():
    gemini = ChatUrlProvider("https://www.google.com/search?q=firefox")
    grok = FakeProvider(response="https://www.mozilla.org/firefox/")

    result = WebResolver(gemini=gemini, grok=grok).resolve_website("firefox")

    assert result is not None
    assert result.url == "https://www.mozilla.org/firefox/"
    assert result.resolver == "grok"
    assert gemini.calls and grok.calls


def test_requested_arbitrary_targets_are_resolved_by_gemini():
    urls = {
        "wikipedia": "https://www.wikipedia.org/",
        "security": "https://www.security.org/",
        "gpt": "https://chatgpt.com/",
        "chat gpt": "https://chatgpt.com/",
        "chat gpd": "https://chatgpt.com/",
        "chat jpt": "https://chatgpt.com/",
        "spotify": "https://www.spotify.com/",
        "netflix": "https://www.netflix.com/",
        "amazon": "https://www.amazon.com/",
    }
    provider = ChatUrlProvider("")
    resolver = WebResolver(gemini=provider)

    for target, url in urls.items():
        provider.response = f"The official website is {url}"
        result = resolver.resolve_website(target)
        assert result is not None, target
        assert result.url == url
        assert "youtube.com/results" not in result.url


def test_wikipedia_is_allowed_when_wikipedia_is_the_requested_target():
    provider = ChatUrlProvider("https://www.wikipedia.org/")

    result = WebResolver(gemini=provider).resolve_website("wikipedia")

    assert result is not None
    assert result.url == "https://www.wikipedia.org/"


def test_chatgpt_speech_variants_resolve_to_the_official_site():
    resolver = WebResolver(gemini=ChatUrlProvider("My conversational AI provider is not configured yet."))

    for target in ("gpt", "chat gpt", "chat gpd", "chat jpt", "chat gptt"):
        result = resolver.resolve_website(target)
        assert result is not None
        assert result.url == "https://chatgpt.com/"


def test_gemini_chat_response_without_http_url_is_rejected():
    provider = ChatUrlProvider("I cannot confidently identify the official website.")

    assert WebResolver(gemini=provider).resolve_website("unknown target") is None


def test_configured_gemini_request_failure_is_not_reported_as_unconfigured():
    provider = FakeProvider(error=RuntimeError("quota exhausted"))

    result = WebResolver(gemini=provider).resolve_website("Example Company")

    assert result is None


def test_gemini_unavailable_message_falls_back_to_known_official_sites():
    provider = ChatUrlProvider("My conversational AI provider is not configured yet.")
    resolver = WebResolver(gemini=provider)

    for target, expected in {
        "google docs": "https://docs.google.com/",
        "pw": "https://www.pw.live/",
        "unacademy": "https://unacademy.com/",
        "udiai": "https://uidai.gov.in/",
        "whatsapp": "https://web.whatsapp.com/",
        "chrome": "https://www.google.com/chrome/",
    }.items():
        result = resolver.resolve_website(target)
        assert result is not None, target
        assert result.url == expected


def test_valid_google_product_url_is_accepted_but_google_search_is_rejected():
    chrome = ChatUrlProvider("https://www.google.com/chrome/")
    assert WebResolver(gemini=chrome).resolve_website("chrome").url == "https://www.google.com/chrome/"

    search = ChatUrlProvider("https://www.google.com/search?q=chrome")
    assert WebResolver(gemini=search).resolve_website("chrome").url == "https://www.google.com/chrome/"


def test_explicit_web_targets_never_resolve_to_youtube_search():
    resolver = WebResolver()
    targets = {
        "unacademy": "https://unacademy.com/",
        "whatsapp": "https://web.whatsapp.com/",
        "gmail": "https://mail.google.com/",
        "google docs": "https://docs.google.com/",
        "chrome": "https://www.google.com/chrome/",
        "pw": "https://www.pw.live/",
        "uidai": "https://uidai.gov.in/",
        "youtube": "https://www.youtube.com/",
    }

    for target, expected in targets.items():
        result = resolver.resolve_website(target)
        assert result is not None
        assert result.url == expected
        assert "youtube.com/results?search_query=" not in result.url


def test_open_web_and_play_use_different_intents():
    assert router.route("open web unacademy").route == WEB_NAVIGATION
    assert router.route("play unacademy").route != WEB_NAVIGATION
    assert SmartBrain(router).decide("open web unacademy").mode == "web_navigation"
    assert SmartBrain(router).decide("play unacademy").mode == "web_media"


def test_grok_is_used_only_when_gemini_fails():
    gemini = ChatUrlProvider("No confident URL")
    grok = FakeProvider(response="Official site: https://www.example.org/")

    result = WebResolver(gemini=gemini, grok=grok).resolve_website("unknown target")

    assert result is not None
    assert result.url == "https://www.example.org/"
    assert gemini.calls and grok.calls


def test_search_or_wikipedia_url_is_rejected():
    for url in (
        "https://www.google.com/search?q=unknown",
        "https://en.wikipedia.org/wiki/Unknown",
    ):
        assert WebResolver(gemini=ChatUrlProvider(url)).resolve_website("unknown target") is None


def test_mismatched_provider_domains_are_not_opened():
    grok = FakeProvider(response=official_payload("https://www.instagram.com/", "instagram.com"))
    gemini = FakeProvider(response=official_payload("https://example.com/instagram", "example.com"))
    assert WebResolver(grok=grok, gemini=gemini).resolve_website("instagram") is None


def test_unsafe_or_mismatched_ai_url_is_rejected():
    grok = FakeProvider(response=official_payload("javascript:alert(1)", "instagram.com"))
    gemini = FakeProvider(response=official_payload("https://example.com/instagram-login", "instagram.com"))
    assert WebResolver(grok=grok, gemini=gemini).resolve_website("instagram") is None


def test_action_executor_rejects_unsafe_open_url():
    executor = ActionExecutor()
    assert executor.execute({"action": "open_url", "target": "javascript:alert(1)"})["success"] is False


def test_assistant_only_sends_explicit_web_requests_to_resolver(monkeypatch):
    import assistant

    spoken = []
    monkeypatch.setattr(assistant, "speak", spoken.append)
    monkeypatch.setattr(assistant, "load_provider_config", lambda: type("Config", (), {
        "configured": False,
        "api_key": "",
        "model": "test",
    })())
    instance = assistant.AccessibilityAssistant(dry_run=True)
    calls = []
    instance.web_resolver.resolve_website = lambda target: calls.append(target) or OfficialSiteResult(
        "Instagram", "https://www.instagram.com/", 0.99, "instagram.com", "gemini", "official"
    )

    assert instance.handle("open web instagram") is True
    assert calls == ["instagram"]
    assert spoken == ["Opening."]
    calls.clear()
    assert instance.handle("open Gmail") is True
    assert calls == []


def test_explicit_web_route_cannot_fall_into_media_handler(monkeypatch):
    import assistant

    monkeypatch.setattr(assistant, "speak", lambda message: None)
    monkeypatch.setattr(assistant, "load_provider_config", lambda: type("Config", (), {
        "configured": False,
        "api_key": "",
        "model": "test",
    })())
    instance = assistant.AccessibilityAssistant(dry_run=True)
    instance.smart_brain.decide = lambda *args, **kwargs: type("Decision", (), {
        "mode": "web_media",
        "query": "unacademy",
    })()
    resolved = []
    instance.web_resolver.resolve_website = lambda target: resolved.append(target) or OfficialSiteResult(
        "Unacademy", "https://unacademy.com/", 0.99, "unacademy.com", "local", "official"
    )
    instance.handle_media_request = lambda decision: (_ for _ in ()).throw(
        AssertionError("explicit WEB intent reached MEDIA handler")
    )

    assert instance.handle("open web unacademy") is True
    assert resolved == ["unacademy"]


def test_assistant_wires_configured_grok_into_web_resolver(monkeypatch):
    import assistant

    grok = FakeProvider(response="https://www.mozilla.org/firefox/")
    grok.configured = True
    monkeypatch.setenv("MARUTI_GROK_LIVE", "1")
    monkeypatch.setattr(assistant, "default_conversation_provider", lambda: None)
    monkeypatch.setattr(assistant, "GrokVisualBrain", lambda **kwargs: grok)
    monkeypatch.setattr(assistant, "load_provider_config", lambda: type("Config", (), {
        "configured": True,
        "api_key": "test-only",
        "model": "test",
    })())

    instance = assistant.AccessibilityAssistant(dry_run=True)

    assert instance.web_resolver.grok is grok


def test_open_web_without_target_asks_for_website(monkeypatch):
    import assistant

    spoken = []
    monkeypatch.setattr(assistant, "speak", spoken.append)
    monkeypatch.setattr(assistant, "load_provider_config", lambda: type("Config", (), {
        "configured": False,
        "api_key": "",
        "model": "test",
    })())
    instance = assistant.AccessibilityAssistant(dry_run=True)
    instance.web_resolver.resolve_website = lambda target: (_ for _ in ()).throw(
        AssertionError("targetless WEB intent attempted resolution")
    )

    assert instance.handle("open web") is True
    assert spoken == ["Which website should I open?"]


def test_generic_open_web_target_uses_official_resolver_without_search_url(monkeypatch):
    resolver = WebResolver()
    monkeypatch.setattr(
        resolver,
        "_search_official_candidates",
        lambda target: [(f"{target} official", "https://example.org/official", 0.9)],
    )

    result = resolver.resolve_website("Maharashtra government")

    assert isinstance(result, OfficialSiteResult)
    assert result.url == "https://example.org/official"
    assert "search" not in result.url
