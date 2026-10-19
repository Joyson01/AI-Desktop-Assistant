import json

from PIL import Image

from brain.intent_router import AMBIGUOUS, COMPUTER_ACTION, CONVERSATION, MIXED, SYSTEM_CONTROL, IntentRouter
from brain.providers.grok_visual_brain import GrokVisualBrain
from brain.screen_context import BrainInput, ScreenContext


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    class Responses:
        def __init__(self, owner):
            self.owner = owner

        def create(self, **kwargs):
            self.owner.calls.append(kwargs)
            return {"output_text": json.dumps(self.owner.response)}

    @property
    def responses(self):
        return self.Responses(self)


def route(text):
    return IntentRouter().route(text)


def test_conversation_examples_route_to_provider_boundary():
    examples = (
        "Tell me about Interstellar",
        "Interstellar movie ke baare mein batao",
        "Prime Minister kaun hai?",
        "भारत के प्रधानमंत्री कौन हैं",
        "who is the prime minister of India",
        "क्रोम क्या है?",
        "Maruti mujhe Hindi mein samjhao",
    )

    for text in examples:
        result = route(text)

        assert result.route == CONVERSATION
        assert result.semantic_intent == "informational_question"
        assert result.conversation_text == text
        assert result.legacy_intent is None


def test_greeting_examples_route_as_conversation():
    examples = (
        ("Maruti hello", "hello"),
        ("hello Maruti", "hello"),
        ("hi Maruti", "hello"),
        ("मारुति कैसे हो", "how_are_you"),
        ("Maruti tum kaise ho?", "how_are_you"),
    )

    for text, semantic in examples:
        result = route(text)

        assert result.route == CONVERSATION
        assert result.semantic_intent == semantic


def test_equivalent_chrome_open_goals_share_semantic_intent_without_losing_original_text():
    examples = (
        "chrome kholo",
        "chrome open karo",
        "open chrome",
        "क्रोम खोलो",
        "bhai chrome khol do",
    )

    results = [route(text) for text in examples]

    assert {result.route for result in results} == {COMPUTER_ACTION}
    assert {result.semantic_intent for result in results} == {"open_chrome"}
    assert {result.normalized_text for result in results} == {"open chrome"}
    assert [result.original_text for result in results] == list(examples)


def test_computer_command_examples_route_without_coordinates_or_execution_data():
    examples = (
        ("Click on Chrome", "click_visual_target"),
        ("Open Chrome", "open_chrome"),
        ("Screen neeche scroll karo", "scroll_down"),
        ("Enter button par click karo", "click_enter_button"),
        ("YouTube kholo aur Saiyaara search karo", "multi_step_computer_action"),
        ("Page reload karo", "reload_page"),
        ("Ctrl+R", "reload_page"),
    )

    for text, semantic in examples:
        result = route(text)

        assert result.route == COMPUTER_ACTION
        assert result.semantic_intent == semantic
        assert "x" not in result.metadata
        assert "y" not in result.metadata


def test_click_phrases_preserve_the_visible_target_text():
    router = IntentRouter()

    for phrase, target in (
        ("click on System", "system"),
        ("click on Motu Patlu", "motu patlu"),
        ("click on Images", "images"),
        ("click on Nehru Yadav", "nehru yadav"),
        ("click Nehru", "nehru"),
        ("click on File button", "file"),
        ("click YouTube", "youtube"),
        ("click on the logo", "logo"),
        ("click three dots", "three dots"),
        ("click cross", "cross"),
        ("click X", "x"),
    ):
        result = router.route(phrase)
        assert result.semantic_intent == "click_visual_target", phrase
        assert result.metadata["target"] == target


def test_click_on_website_text_targets_the_visible_words():
    result = IntentRouter().route("click on website developer")

    assert result.route == COMPUTER_ACTION
    assert result.semantic_intent == "click_visual_target"
    assert result.metadata["target"] == "website developer"


def test_click_targets_strip_button_logo_and_location_noise():
    for phrase, target in (
        ("click on the Search button in the top right", "search"),
        ("click on the Google logo at the top left", "google"),
        ("click the login button near the menu", "login"),
        ("click on the settings text in the sidebar", "settings"),
    ):
        result = IntentRouter().route(phrase)
        assert result.semantic_intent == "click_visual_target", phrase
        assert result.metadata["target"] == target, (phrase, result.metadata)


def test_click_and_right_click_extract_arbitrary_targets():
    for command, action, target in (
        ("click on Settings", "click_visual_target", "settings"),
        ("click Settings", "click_visual_target", "settings"),
        ("click on Account Settings", "click_visual_target", "account settings"),
        ("click on the Settings button", "click_visual_target", "settings"),
        ("right click on Settings", "right_click", "settings"),
        ("right click on Account Settings", "right_click", "account settings"),
        ("File par right click karo", "right_click", "file"),
    ):
        result = route(command)
        assert result.semantic_intent == action
        assert result.metadata["target"] == target


def test_hinglish_click_does_not_include_command_words_in_target():
    for command in ("Settings par click karo", "Settings par click", "Settings on click karo"):
        result = route(command)
        assert result.semantic_intent == "click_visual_target"
        assert result.metadata["target"] == "settings"


def test_hold_release_and_relative_move_commands_route():
    assert route("hold left click").metadata == {"action": "mouse_down", "button": "left"}
    assert route("release left mouse button").metadata == {"action": "mouse_up", "button": "left"}
    assert route("go left").metadata["direction"] == "left"
    assert route("go right").metadata["direction"] == "right"


def test_system_control_examples_route_to_system_control_intent():
    examples = (
        ("bluetooth on", "bluetooth", "set", "on", 0.98),
        ("bluetooth off", "bluetooth", "set", "off", 0.98),
        ("turn bluetooth on", "bluetooth", "set", "on", 0.98),
        ("bluetooth chalu karo", "bluetooth", "set", "on", 0.96),
        ("ब्लूटूथ चालू करो", "bluetooth", "set", "on", 0.96),
        ("wifi on", "wifi", "set", "on", 0.98),
        ("wifi off", "wifi", "set", "off", 0.98),
        ("वाईफाई चालू करो", "wifi", "set", "on", 0.96),
        ("brightness 70 percent", "brightness", "set", 70, 0.98),
        ("set brightness to 70", "brightness", "set", 70, 0.98),
        ("volume 50 percent", "volume", "set", 50, 0.98),
        ("mute", "volume", "set", "mute", 0.98),
        ("unmute", "volume", "set", "unmute", 0.98),
        ("system settings kholo", "settings", "open", None, 0.96),
        ("display settings kholo", "display", "open", None, 0.96),
        ("sound settings kholo", "sound", "open", None, 0.96),
    )

    for text, action, operation, value, min_conf in examples:
        result = route(text)

        assert result.route == SYSTEM_CONTROL, text
        assert result.metadata.get("system_action") == action, (text, result.metadata)
        assert result.metadata.get("operation") == operation, (text, result.metadata)
        if value is None:
            assert result.metadata.get("value") is None
        else:
            assert result.metadata.get("value") == value, (text, result.metadata)
        assert result.confidence >= min_conf, (text, result.confidence)


def test_ambiguous_request_asks_for_clarification_without_legacy_intent():
    for text in ("Chrome", "click", "search"):
        result = route(text)

        assert result.route == AMBIGUOUS
        assert result.legacy_intent is None
        assert "not sure" in result.clarification


def test_mixed_conversation_and_computer_action_is_not_executed_by_router():
    result = route("Chrome kholo aur phir mujhe batao Prime Minister kaun hai.")

    assert result.route == MIXED
    assert result.semantic_intent == "mixed_computer_and_conversation"
    assert result.computer_goal == "Chrome kholo aur phir mujhe batao Prime Minister kaun hai."
    assert result.conversation_text == "Chrome kholo aur phir mujhe batao Prime Minister kaun hai."
    assert result.parts[0]["route"] == COMPUTER_ACTION
    assert result.parts[1]["route"] == CONVERSATION


def test_routed_multistep_computer_goal_still_returns_one_next_visual_action():
    result = route("YouTube kholo aur Saiyaara search karo")
    transport = FakeTransport({"action": "click", "x": 80, "y": 90, "confidence": 0.95})
    brain = GrokVisualBrain(transport=transport)
    brain_input = BrainInput(
        goal=result.computer_goal,
        screen=ScreenContext(Image.new("RGB", (800, 600), "white")),
    )

    visual_result = brain.analyze(brain_input)

    assert result.route == COMPUTER_ACTION
    assert visual_result.action.to_dict() == {"action": "click", "x": 80, "y": 90}
    assert visual_result.action.text is None
    assert len(transport.calls) == 1
    request_text = json.loads(transport.calls[0]["input"][1]["content"][0]["text"])
    assert request_text["goal"] == "YouTube kholo aur Saiyaara search karo"
