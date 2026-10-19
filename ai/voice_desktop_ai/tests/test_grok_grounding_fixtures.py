import json

from PIL import Image

from brain.providers.grok_visual_brain import GrokVisualBrain
from brain.screen_context import BrainInput, ScreenContext
from brain.task_orchestrator import TaskOrchestrator
from computer.actions import ActionValidator
from tests.fixtures.fake_executor import FakeExecutor
from verification.verifier import RuleBasedVerifier


class FixtureTransport:
    def __init__(self, response):
        self.response_queue = list(response) if isinstance(response, list) else [response]
        self.calls = []

    class Responses:
        def __init__(self, owner):
            self.owner = owner

        def create(self, **kwargs):
            self.owner.calls.append(kwargs)
            response = self.owner.response_queue.pop(0)
            return {"output_text": json.dumps(response)}

    @property
    def responses(self):
        return self.Responses(self)


def visual_input(goal, label):
    return BrainInput(
        goal=goal,
        screen=ScreenContext(
            screenshot=Image.new("RGB", (800, 600), "white"),
            active_application="fixture",
            active_window=label,
            ocr_text=(),
            uia_metadata=(),
        ),
    )


def run_fixture(goal, label, response):
    transport = FixtureTransport(response)
    brain = GrokVisualBrain(transport=transport)
    result = brain.analyze(visual_input(goal, label))
    return result, transport


def test_visible_chrome_fixture_returns_valid_click_without_ocr_or_uia():
    result, transport = run_fixture(
        "open Chrome", "visible-chrome-icon", {"action": "click", "x": 80, "y": 90, "confidence": 0.95}
    )

    assert result.action.name == "click"
    assert ActionValidator.validate(result.action.to_dict(), (800, 600))[0]
    assert result.action.to_dict()["x"] == 80
    assert transport.calls[0]["input"][1]["content"][1]["type"] == "input_image"
    request_text = json.loads(transport.calls[0]["input"][1]["content"][0]["text"])
    assert request_text["screen"]["ocr_text"] == []
    assert request_text["screen"]["uia_metadata"] == []


def test_equivalent_english_hindi_hinglish_chrome_goals_return_valid_clicks():
    for goal in (
        "Click on Chrome",
        "Chrome kholo",
        "Chrome open karo",
        "क्रोम खोलो",
    ):
        result, transport = run_fixture(
            goal,
            "visible-chrome-icon",
            {"action": "click", "x": 80, "y": 90, "confidence": 0.95},
        )

        assert result.action.to_dict() == {"action": "click", "x": 80, "y": 90}
        assert ActionValidator.validate(result.action.to_dict(), (800, 600))[0]
        request_text = json.loads(transport.calls[0]["input"][1]["content"][0]["text"])
        assert request_text["goal"] == goal


def test_visible_enter_fixture_returns_click():
    result, _ = run_fixture(
        "click on the Enter button", "visible-enter-button", {"action": "click", "x": 410, "y": 510, "confidence": 0.92}
    )

    assert result.action.to_dict() == {"action": "click", "x": 410, "y": 510}


def test_hinglish_enter_button_goal_returns_click():
    result, transport = run_fixture(
        "Enter button par click karo",
        "visible-enter-button",
        {"action": "click", "x": 410, "y": 510, "confidence": 0.92},
    )

    assert result.action.to_dict() == {"action": "click", "x": 410, "y": 510}
    request_text = json.loads(transport.calls[0]["input"][1]["content"][0]["text"])
    assert request_text["goal"] == "Enter button par click karo"


def test_search_fixture_returns_only_the_next_action():
    result, _ = run_fixture(
        "open Chrome, search YouTube and search Saiyaara",
        "visible-browser-search-box",
        {"action": "click", "x": 500, "y": 50, "confidence": 0.9},
    )

    assert result.action.name == "click"
    assert result.action.text is None


def test_hinglish_youtube_search_goal_returns_only_one_next_action():
    result, transport = run_fixture(
        "YouTube kholo aur Saiyaara search karo",
        "visible-chrome-icon",
        {"action": "click", "x": 80, "y": 90, "confidence": 0.95},
    )

    assert result.action.to_dict() == {"action": "click", "x": 80, "y": 90}
    assert len(transport.calls) == 1
    assert "text" not in result.action.to_dict()
    assert "key" not in result.action.to_dict()


def test_visible_search_box_fixture_returns_next_click_or_type_action():
    for response in (
        {"action": "click", "x": 500, "y": 50, "confidence": 0.9},
        {"action": "type", "text": "Saiyaara", "confidence": 0.95},
    ):
        result, _ = run_fixture("search Saiyaara", "visible-browser-search-box", response)

        assert result.action.name in {"click", "type"}
        assert ActionValidator.validate(result.action.to_dict(), (800, 600))[0]


def test_keyboard_fixture_returns_valid_ctrl_r_action():
    result, _ = run_fixture("reload the page", "visible-browser", {"action": "hotkey", "keys": ["ctrl", "r"], "confidence": 1.0})

    assert result.action.to_dict() == {"action": "hotkey", "keys": ["ctrl", "r"]}


def test_equivalent_reload_goals_return_valid_ctrl_r_action():
    for goal in ("Page reload karo", "Ctrl+R"):
        result, transport = run_fixture(
            goal,
            "visible-browser",
            {"action": "hotkey", "keys": ["ctrl", "r"], "confidence": 1.0},
        )

        assert result.action.to_dict() == {"action": "hotkey", "keys": ["ctrl", "r"]}
        assert ActionValidator.validate(result.action.to_dict(), (800, 600))[0]
        request_text = json.loads(transport.calls[0]["input"][1]["content"][0]["text"])
        assert request_text["goal"] == goal


def test_missing_and_ambiguous_visual_targets_return_ask_user():
    for goal, label, message in (
        ("click Bluetooth", "desktop-without-bluetooth", "Bluetooth is not visible."),
        ("click YouTube", "youtube-youtube-music-youtube-studio", "Which YouTube target do you mean?"),
    ):
        result, _ = run_fixture(goal, label, {"action": "ask_user", "message": message, "confidence": 0.0})

        assert result.action.name == "ask_user"
        assert result.confidence == 0.0


def test_invalid_click_coordinates_are_rejected_by_validator():
    for coordinates in ((-1, 10), (800, 10), (10, 600), ("10", 10)):
        payload = {"action": "click", "x": coordinates[0], "y": coordinates[1]}
        assert ActionValidator.validate(payload, (800, 600))[0] is False


def test_multi_step_goal_returns_exactly_one_next_action():
    result, transport = run_fixture(
        "open Chrome, click the search box, type Saiyaara, and press Enter",
        "visible-chrome-icon",
        {"action": "click", "x": 80, "y": 90, "confidence": 0.95},
    )

    assert result.action.to_dict() == {"action": "click", "x": 80, "y": 90}
    assert len(transport.calls) == 1
    assert "type" not in result.action.to_dict()


def test_expected_state_propagates_to_semantic_verification():
    transport = FixtureTransport([
        {
            "action": "click",
            "x": 80,
            "y": 90,
            "confidence": 0.95,
            "expected_state": {"active_application": "Chrome"},
        },
        {"action": "done", "message": "Chrome is open.", "confidence": 1.0},
    ])
    brain = GrokVisualBrain(transport=transport)
    executor = FakeExecutor()
    screens = iter((
        ScreenContext(Image.new("RGB", (800, 600), "white"), active_application="Desktop"),
        ScreenContext(Image.new("RGB", (800, 600), "white"), active_application="Chrome"),
    ))

    def verify_expected_state(before, after, action, result, state):
        return RuleBasedVerifier().verify(before, after, state.expected_state)

    orchestrator = TaskOrchestrator(
        brain,
        executor,
        lambda: next(screens),
        verifier=verify_expected_state,
        max_steps=2,
    )

    state = orchestrator.run("open Chrome")

    assert state.status == "completed"
    assert state.action_history[0]["result"]["verification"] == "success"
    assert state.action_history[0]["result"]["verification_result"]["expected_state"] == {"active_application": "Chrome"}
    assert executor.calls == [{"action": "click", "target": {"x": 80, "y": 90}}]


def test_visual_fixture_request_contains_all_grounding_instructions():
    brain = GrokVisualBrain(transport=FixtureTransport({"action": "done", "message": "complete"}))
    request = brain._build_request(visual_input("open Chrome and search Saiyaara", "desktop"))
    prompt = request[0]["content"].lower()

    for phrase in (
        "english, hindi",
        "hinglish/roman hindi",
        "interpret the goal's meaning",
        "visually analyze the screenshot",
        "inspect the attached screenshot visually",
        "locate the requested ui element visually",
        "do not rely only on ocr",
        "ocr alone",
        "never invent coordinates",
        "relative to the supplied screenshot",
        "coordinates are relative to screenshot dimensions",
        "return only the next action",
        "return ask_user",
        "exactly one next action",
        "after each action a new screenshot is supplied",
    ):
        assert phrase in prompt
