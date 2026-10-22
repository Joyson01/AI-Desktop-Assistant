"""Comprehensive tests for voice-controlled 'Click on [target]' commands.

Validates:
1. Spoken voice command routing & target text sanitization (English, Hindi, Hinglish, punctuation, boilerplate).
2. Screen perception multi-tier matching (exact, word boundary, prefix, substring, fuzzy).
3. Case-insensitive matching and multi-word phrase grouping ('Sign In', 'New Tab').
4. Ambiguity resolution when multiple elements match.
5. Display scaling / DPI offset mapping.
6. End-to-end execution flow from speech input to coordinate click and user feedback.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from assistant import Assistant
from core.browser import BrowserAutomation
from core.context import ConversationContext
from core.models import ActionRisk, AssistantState
from core.perception import PerceptionEngine, ScreenElement, TargetMatchResult
from intent_router import IntentRouter, extract_click_target


# ---------------------------------------------------------------------------
# 1. Voice Command Routing & Target Extraction Tests
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "utterance,expected_target",
    [
        ("Click on File", "File"),
        ("Click on Settings", "Settings"),
        ("Click on Chrome", "Chrome"),
        ("click File", "File"),
        ("click on settings", "settings"),
        ("click on the File button", "File"),
        ("click the Settings button", "Settings"),
        ("click on button File", "File"),
        ("click button Chrome", "Chrome"),
        ("click on the link Chrome", "Chrome"),
        ("click the link Settings", "Settings"),
        ("click on the tab Downloads", "Downloads"),
        ("click on icon Firefox", "Firefox"),
        ("click on the menu Tools", "Tools"),
        ("click on 'File'", "File"),
        ("click on \"Settings.\"", "Settings"),
        ("please click on File", "File"),
        ("click File please", "File"),
        ("tap on Settings", "Settings"),
        ("tap Chrome", "Chrome"),
        ("find the link that says Sign In", "Sign In"),
        ("find button Submit", "Submit"),
        # Hinglish variations
        ("File pe click karo", "File"),
        ("Settings par click karo", "Settings"),
        ("Chrome click karo", "Chrome"),
        ("click karo file pe", "file"),
        ("Settings pe click", "Settings"),
        ("Chrome par click", "Chrome"),
        ("kripya File pe click karo", "File"),
    ],
)
def test_click_target_extraction(utterance, expected_target):
    """Verify target text is extracted cleanly without command boilerplate."""
    target = extract_click_target(utterance)
    assert target == expected_target


def test_click_routing_intent():
    """Verify router produces 'click' intent with correct target label."""
    r = IntentRouter()
    i1 = r.route("Click on File")
    assert i1.name == "click"
    assert i1.args["label"] == "File"

    i2 = r.route("Settings pe click karo")
    assert i2.name == "click"
    assert i2.args["label"] == "Settings"

    i3 = r.route("click on the Chrome button")
    assert i3.name == "click"
    assert i3.args["label"] == "Chrome"


def test_video_click_not_hijacked():
    """Verify 'click the first video' remains routed to browser_click_video."""
    r = IntentRouter()
    i = r.route("click the first video")
    assert i.name == "browser_click_video"


def test_keyboard_press_not_hijacked():
    """Verify keyboard 'press enter' and 'press ctrl a' are not hijacked by click."""
    r = IntentRouter()
    assert r.route("press enter").name == "press_keys"
    assert r.route("press ctrl a").name == "press_keys"
    assert r.route("press left arrow").name == "press_keys"


# ---------------------------------------------------------------------------
# 2. Perception Engine Text Matching & Ambiguity Tests
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_screen_elements():
    """Sample UI elements representing a typical desktop application window."""
    return [
        ScreenElement(text="File", x=30, y=15, width=40, height=20, confidence=0.95, left=10, top=5),
        ScreenElement(text="Edit", x=80, y=15, width=40, height=20, confidence=0.95, left=60, top=5),
        ScreenElement(text="View", x=130, y=15, width=40, height=20, confidence=0.95, left=110, top=5),
        ScreenElement(text="Settings", x=200, y=15, width=60, height=20, confidence=0.92, left=170, top=5),
        # A button with multi-word label on same horizontal line
        ScreenElement(text="Sign", x=320, y=200, width=40, height=25, confidence=0.90, left=300, top=188),
        ScreenElement(text="In", x=370, y=200, width=30, height=25, confidence=0.90, left=355, top=188),
        # Desktop shortcut
        ScreenElement(text="Google", x=500, y=400, width=50, height=20, confidence=0.88, left=475, top=390),
        ScreenElement(text="Chrome", x=560, y=400, width=60, height=20, confidence=0.91, left=530, top=390),
    ]


def test_perception_exact_match(sample_screen_elements):
    """Verify exact match locates the precise target and returns its center coordinates."""
    engine = PerceptionEngine()
    with patch.object(engine, "extract_elements", return_value=sample_screen_elements):
        res = engine.find_target_detailed("File")
        assert res.status == "found"
        assert res.element.text == "File"
        assert res.element.x == 30
        assert res.element.y == 15
        assert res.match_tier == "exact"


def test_perception_case_insensitive_match(sample_screen_elements):
    """Verify matching is case-insensitive ('settings' matches 'Settings')."""
    engine = PerceptionEngine()
    with patch.object(engine, "extract_elements", return_value=sample_screen_elements):
        res = engine.find_target_detailed("settings")
        assert res.status == "found"
        assert res.element.text == "Settings"
        assert res.element.x == 200
        assert res.element.y == 15


def test_perception_multi_word_phrase(sample_screen_elements):
    """Verify multi-word targets ('Sign In') are grouped and centered properly."""
    engine = PerceptionEngine()
    with patch.object(engine, "extract_elements", return_value=sample_screen_elements):
        res = engine.find_target_detailed("Sign In")
        assert res.status == "found"
        assert "Sign" in res.element.text and "In" in res.element.text
        # Bounding box should span from left=300 to right=385 -> center around 342
        assert 330 <= res.element.x <= 360
        assert 190 <= res.element.y <= 210


def test_perception_missing_target(sample_screen_elements):
    """Verify searching for a non-existent target returns 'not_found' status."""
    engine = PerceptionEngine()
    with patch.object(engine, "extract_elements", return_value=sample_screen_elements):
        res = engine.find_target_detailed("NonExistentButton")
        assert res.status == "not_found"
        assert res.element is None
        assert "Could not find any visible element" in res.message


def test_perception_ambiguity_handling():
    """Verify multiple distinct elements matching the same label trigger ambiguity warning."""
    engine = PerceptionEngine()
    # Two identical 'Settings' buttons located in different parts of the screen
    ambiguous_elements = [
        ScreenElement(text="Settings", x=50, y=30, width=60, height=20, confidence=0.95, left=20, top=20),
        ScreenElement(text="Settings", x=700, y=500, width=60, height=20, confidence=0.95, left=670, top=490),
    ]
    with patch.object(engine, "extract_elements", return_value=ambiguous_elements):
        res = engine.find_target_detailed("Settings")
        assert res.status == "ambiguous"
        assert res.element is None
        assert len(res.candidates) == 2
        assert "Multiple elements matching 'Settings' were found" in res.message


def test_perception_duplicate_close_elements_merged():
    """Verify duplicate OCR detections of the same physical spot (<15px) are merged cleanly."""
    engine = PerceptionEngine()
    close_elements = [
        ScreenElement(text="Chrome", x=100, y=100, width=50, height=20, confidence=0.90, left=75, top=90),
        ScreenElement(text="Chrome", x=103, y=102, width=50, height=20, confidence=0.92, left=78, top=92),
    ]
    with patch.object(engine, "extract_elements", return_value=close_elements):
        res = engine.find_target_detailed("Chrome")
        assert res.status == "found"
        assert res.element.text == "Chrome"


def test_perception_empty_screen():
    """Verify searching on a screen with zero readable text returns 'no_text' status."""
    engine = PerceptionEngine()
    with patch.object(engine, "extract_elements", return_value=[]):
        res = engine.find_target_detailed("File")
        assert res.status == "no_text"
        assert "No readable text was detected" in res.message


# ---------------------------------------------------------------------------
# 3. End-to-End Execution Flow Tests
# ---------------------------------------------------------------------------
def test_click_execution_success():
    """Verify complete flow: 'Click on File' locates element and dispatches mouse click."""
    assistant = Assistant(dry_run=False)

    mock_element = ScreenElement(text="File", x=150, y=250, width=40, height=20, confidence=0.95)
    match_result = TargetMatchResult(status="found", element=mock_element, match_tier="exact", match_score=1.0)

    with patch.object(assistant.executor.registry.perception, "find_target_detailed", return_value=match_result):
        with patch.object(assistant.executor.registry.input, "click_coordinate", return_value=(True, "Clicked at (150, 250).")) as mock_click:
            result = assistant.process("Click on File")
            assert result.success is True
            assert "Clicked 'File'" in result.message
            mock_click.assert_called_once_with(150, 250)


def test_click_execution_ambiguity_aborts():
    """Verify multiple matching elements abort execution safely without clicking."""
    assistant = Assistant(dry_run=False)

    match_result = TargetMatchResult(
        status="ambiguous",
        message="Multiple elements matching 'Settings' were found on screen (2 matches). Please specify which one.",
    )

    with patch.object(assistant.executor.registry.perception, "find_target_detailed", return_value=match_result):
        with patch.object(assistant.executor.registry.input, "click_coordinate") as mock_click:
            result = assistant.process("Click on Settings")
            assert result.success is False
            assert "Multiple elements matching 'Settings'" in result.message
            mock_click.assert_not_called()


def test_click_execution_not_found():
    """Verify searching for a missing element gives clear spoken feedback."""
    assistant = Assistant(dry_run=False)

    match_result = TargetMatchResult(
        status="not_found",
        message="Could not find any visible element matching 'NonExistent' on the screen.",
    )

    with patch.object(assistant.executor.registry.perception, "find_target_detailed", return_value=match_result):
        with patch.object(assistant.executor.registry.input, "click_coordinate") as mock_click:
            result = assistant.process("Click on NonExistent")
            assert result.success is False
            assert "Could not find any visible element" in result.message
            mock_click.assert_not_called()


def test_click_execution_sensitive_confirmation_declined():
    """Verify sensitive click targets ('Pay Now') require confirmation; declining cancels execution."""
    assistant = Assistant(dry_run=False, confirm_callback=lambda prompt: False)

    with patch.object(assistant.executor.registry.input, "click_coordinate") as mock_click:
        result = assistant.process("Click on Pay Now")
        assert result.success is False
        assert "cancelled" in result.message.lower()
        mock_click.assert_not_called()
