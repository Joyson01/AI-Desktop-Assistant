"""Comprehensive unit test suite for MARUTI desktop automation upgrades.

Covers:
1. Intent recognition & normalization for English, Hindi, and Hinglish.
2. Exact volume percentages, relative volume changes, clamping, and mute states.
3. Audio controller backend operations & mock failure handling.
4. Safe application, folder, and URL launching (prohibiting dangerous schemes).
5. Bounded scrolling, repetition clamping, and coordinate bounds validation.
6. Browser video targeting and sensitive action confirmation.
7. Safety policy engine enforcement (safe vs sensitive).
8. MCP tool registry schema validation, error handling, and policy gates.
9. Command debouncing / duplicate suppression.
10. PySide6 worker thread responsiveness and cleanup.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
import pytest

from actions import ActionExecutor
from brain import Brain
from core.action_registry import CentralActionRegistry
from core.audio import AudioController
from core.browser import BrowserAutomation
from core.context import ConversationContext
from core.input import DesktopInputBackend
from core.mcp import MCPTool, MCPToolRegistry, create_default_mcp_registry
from core.perception import PerceptionEngine, ScreenElement
from core.policy import ActionRisk, ActionResult, PolicyEngine
from core.system_control import SystemController
from gui.app import CommandDebouncer
from intent_router import IntentRouter


@pytest.fixture
def router():
    return IntentRouter()


@pytest.fixture
def executor():
    return ActionExecutor(Brain(), dry_run=True)


# ---------------------------------------------------------------------------
# 1 & 2. Intent recognition for Volume, Folders, Scrolling, Perception
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected_name,expected_args", [
    # Absolute volume
    ("set volume to 50 percent", "volume_set", {"percent": 50.0}),
    ("set volume to 80%", "volume_set", {"percent": 80.0}),
    ("volume 50 kar do", "volume_set", {"percent": 50.0}),
    ("volume 50", "volume_set", {"percent": 50.0}),
    ("set volume to zero", "volume_set", {"percent": 0.0}),
    ("set volume to maximum", "volume_set", {"percent": 100.0}),
    ("full volume", "volume_set", {"percent": 100.0}),
    # Relative volume
    ("volume low", "volume_change", {"delta": -15.0}),
    ("lower the volume", "volume_change", {"delta": -15.0}),
    ("volume kam karo", "volume_change", {"delta": -15.0}),
    ("increase volume", "volume_change", {"delta": 15.0}),
    ("volume badhao", "volume_change", {"delta": 15.0}),
    ("increase volume by 10 percent", "volume_change", {"delta": 10.0}),
    ("lower volume by 20 percent", "volume_change", {"delta": -20.0}),
    # Mute / Unmute
    ("mute", "volume_mute", {"state": True}),
    ("unmute", "volume_mute", {"state": False}),
    ("awaaz band karo", "volume_mute", {"state": True}),
    ("awaaz chalu karo", "volume_mute", {"state": False}),
    # Folders
    ("open downloads", "open_folder", {"folder": "downloads"}),
    ("open documents", "open_folder", {"folder": "documents"}),
    ("open desktop", "open_folder", {"folder": "desktop"}),
    ("open home", "open_folder", {"folder": "home"}),
    ("downloads folder kholo", "open_folder", {"folder": "downloads"}),
    # Enhanced Scrolling
    ("scroll down a little", "scroll", {"direction": "down", "amount": 200, "qualifier": "little"}),
    ("thoda neeche scroll karo", "scroll", {"direction": "down", "amount": 200, "qualifier": "little"}),
    ("scroll up a lot", "scroll", {"direction": "up", "amount": 800, "qualifier": "lot"}),
    ("bahut upar scroll karo", "scroll", {"direction": "up", "amount": 800, "qualifier": "lot"}),
    ("scroll down 3 times", "scroll", {"direction": "down", "amount": 400, "repetitions": 3}),
    # Perception & Video
    ("click the first video", "browser_click_video", {}),
    ("pehla video kholo", "browser_click_video", {}),
    ("find the first video", "browser_click_video", {}),
    ("what is on my screen", "inspect_screen", {}),
    ("screen pe kya hai", "inspect_screen", {}),
    ("read the visible text", "read_screen", {}),
    ("screen ka text padho", "read_screen", {}),
])
def test_new_intents_routing(router, text, expected_name, expected_args):
    intent = router.route(text)
    assert intent.name == expected_name, f"For {text!r}, got {intent.name!r}"
    for k, v in expected_args.items():
        assert intent.args.get(k) == v, f"For {text!r}, arg {k!r}: expected {v}, got {intent.args.get(k)}"


# ---------------------------------------------------------------------------
# 3 & 4. Audio Controller, Clamping & Verification
# ---------------------------------------------------------------------------
def test_audio_controller_clamping():
    ac = AudioController(preferred_backend="wpctl")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Volume: 1.00")
        # Over 100% clamped to 100%
        ok, msg = ac.set_volume(150.0)
        assert ok is True
        first_args = mock_run.call_args_list[0][0][0]
        assert "1.00" in first_args

        mock_run.reset_mock()
        # Under 0% clamped to 0%
        ok, msg = ac.set_volume(-50.0)
        assert ok is True
        first_args = mock_run.call_args_list[0][0][0]
        assert "0.00" in first_args


def test_audio_controller_failure_handling():
    ac = AudioController(preferred_backend="wpctl")
    with patch("subprocess.run", side_effect=RuntimeError("PipeWire socket error")):
        ok, msg = ac.set_volume(50.0)
        assert ok is False
        assert "Failed" in msg


# ---------------------------------------------------------------------------
# 5. Website & Application URL Validation & Security
# ---------------------------------------------------------------------------
def test_url_validation_rejects_dangerous_schemes():
    sc = SystemController()

    # Safe schemes
    valid, url, netloc = sc.validate_url("https://www.youtube.com")
    assert valid is True
    assert netloc == "www.youtube.com"

    valid, url, netloc = sc.validate_url("google.com")
    assert valid is True
    assert url == "https://google.com"

    # Dangerous schemes rejected
    valid, err, _ = sc.validate_url("javascript:alert(1)")
    assert valid is False
    assert "Unsupported or dangerous" in err

    valid, err, _ = sc.validate_url("file:///etc/passwd")
    assert valid is False
    assert "Unsupported or dangerous" in err

    valid, err, _ = sc.validate_url("data:text/html,<h1>hack</h1>")
    assert valid is False
    assert "Unsupported or dangerous" in err


def test_open_folder_validation():
    sc = SystemController()
    # Known folders
    ok, msg = sc.open_folder("downloads")
    assert "Downloads" in msg or "Opening" in msg

    # Nonexistent folder
    ok, msg = sc.open_folder("nonexistent_fake_dir_xyz_123")
    assert ok is False


# ---------------------------------------------------------------------------
# 6. Bounded Scrolling & Coordinate Validation
# ---------------------------------------------------------------------------
def test_input_backend_bounded_scrolling():
    backend = DesktopInputBackend()
    backend._pg = MagicMock()

    # Normal scroll
    ok, msg = backend.scroll(direction="down", amount=500, repetitions=1)
    assert ok is True
    assert backend.pg.scroll.call_count == 1
    backend.pg.scroll.assert_called_with(-500)

    # Clamped repetitions: 9999 repetitions clamped to 10
    backend.pg.scroll.reset_mock()
    ok, msg = backend.scroll(direction="up", amount=400, repetitions=9999)
    assert ok is True
    assert backend.pg.scroll.call_count == 10  # Max repetitions = 10

    # Clamped scroll amount: 50000 clamped to 2000
    backend.pg.scroll.reset_mock()
    backend.scroll(direction="down", amount=50000, repetitions=1)
    backend.pg.scroll.assert_called_with(-2000)


def test_coordinate_validation():
    backend = DesktopInputBackend()
    backend._screen_width = 1920
    backend._screen_height = 1080
    backend._pg = MagicMock()

    # Inside screen
    ok, msg = backend.click_coordinate(500, 400)
    assert ok is True

    # Out of bounds
    ok, msg = backend.click_coordinate(2500, 500)
    assert ok is False
    assert "outside the screen resolution" in msg

    ok, msg = backend.click_coordinate(-10, 500)
    assert ok is False


# ---------------------------------------------------------------------------
# 7 & 8. Browser Video Targeting & Perception
# ---------------------------------------------------------------------------
def test_browser_first_video_targeting():
    browser = BrowserAutomation()
    # Mock perception returning a detected video element
    browser.perception.find_first_video = MagicMock(return_value=ScreenElement(
        text="Python Full Course",
        x=450,
        y=320,
        width=300,
        height=180,
        confidence=0.92,
        kind="video",
    ))
    browser.input.click_coordinate = MagicMock(return_value=(True, "Clicked"))

    ok, msg = browser.click_first_video()
    assert ok is True
    assert "first video" in msg.lower()
    browser.input.click_coordinate.assert_called_with(450, 320)


def test_sensitive_click_confirmation():
    policy = PolicyEngine(confirm_callback=lambda prompt: False)  # User declines
    browser = BrowserAutomation(policy=policy)

    # Clicking 'Pay Now' is a sensitive financial action
    ok, msg = browser.click_element_by_label("Pay Now $50")
    assert ok is False
    assert "Cancelled" in msg


# ---------------------------------------------------------------------------
# 9. Policy Engine (Safe vs Sensitive & Non-Overrideable)
# ---------------------------------------------------------------------------
def test_policy_engine_risk_classification():
    policy = PolicyEngine()

    assert policy.classify_risk("open") == ActionRisk.SAFE
    assert policy.classify_risk("scroll") == ActionRisk.SAFE
    assert policy.classify_risk("volume_set") == ActionRisk.SAFE
    assert policy.classify_risk("close_window") == ActionRisk.SENSITIVE
    assert policy.classify_risk("delete_file") == ActionRisk.SENSITIVE

    # Args inspection detecting dangerous commands
    assert policy.classify_risk("run_action", {"cmd": "rm -rf /"}) == ActionRisk.SENSITIVE


def test_policy_confirmation_enforced():
    # When user says Yes
    policy_yes = PolicyEngine(confirm_callback=lambda p: True)
    assert policy_yes.authorize_execution("close_window") is True

    # When user says No
    policy_no = PolicyEngine(confirm_callback=lambda p: False)
    assert policy_no.authorize_execution("close_window") is False


# ---------------------------------------------------------------------------
# 10. MCP Tool Integration, Validation & Execution
# ---------------------------------------------------------------------------
def test_mcp_tool_argument_validation():
    registry = MCPToolRegistry()
    tool = MCPTool(
        name="set_volume",
        description="Set volume",
        input_schema={
            "type": "object",
            "properties": {"percent": {"type": "number"}},
            "required": ["percent"],
        },
        handler=lambda percent: f"Volume: {percent}",
    )
    registry.register_tool(tool)

    # Valid args
    res = registry.execute_tool("set_volume", {"percent": 75})
    assert res["success"] is True
    assert res["result"] == "Volume: 75"

    # Missing required arg
    res = registry.execute_tool("set_volume", {})
    assert res["success"] is False
    assert "Missing required argument" in res["error"]

    # Wrong type
    res = registry.execute_tool("set_volume", {"percent": "not_a_number"})
    assert res["success"] is False
    assert "expected number" in res["error"]


def test_mcp_sensitive_tool_policy_gate():
    policy = PolicyEngine(confirm_callback=lambda p: False)  # Disallowed
    registry = MCPToolRegistry(policy=policy)
    sensitive_tool = MCPTool(
        name="delete_account",
        description="Delete user account",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: "deleted",
        risk_level=ActionRisk.SENSITIVE,
    )
    registry.register_tool(sensitive_tool)

    res = registry.execute_tool("delete_account", {})
    assert res["success"] is False
    assert "was not confirmed" in res["error"]


# ---------------------------------------------------------------------------
# 11. Command Debouncing / Duplicate Suppression
# ---------------------------------------------------------------------------
def test_command_debouncer():
    debouncer = CommandDebouncer(window_sec=1.0)

    # First time -> allowed
    assert debouncer.is_duplicate("open chrome") is False

    # Immediate repetition -> suppressed
    assert debouncer.is_duplicate("open chrome") is True
    assert debouncer.is_duplicate("OPEN CHROME") is True

    # Different command -> allowed
    assert debouncer.is_duplicate("scroll down") is False

    # After window expiration -> allowed
    time.sleep(1.05)
    assert debouncer.is_duplicate("scroll down") is False


# ---------------------------------------------------------------------------
# 12. Context-Aware Sequential Workflow End-to-End
# ---------------------------------------------------------------------------
def test_context_aware_sequential_workflow(router):
    """Test the complete sequential user workflow:
    1. 'Open YouTube.'
    2. 'Search songs.'
    3. 'Search Arijit Singh romantic songs.'
    4. 'Click the first video.'
    5. 'Pause.'
    6. 'Resume.'
    7. 'Scroll down.'
    8. 'Open the second video.'
    """
    ctx = ConversationContext()
    executor = ActionExecutor(Brain(), dry_run=True, context=ctx)

    # Step 1: Open YouTube
    cmd1 = "open youtube"
    i1 = router.route(cmd1, context=ctx)
    assert i1.name == "open"
    assert "youtube" in i1.args.get("target", "")
    reply1 = executor.execute(i1)
    assert "youtube" in reply1.lower()
    # Simulate website navigation context update
    ctx.update_site("youtube", "https://www.youtube.com", page_state="homepage")
    assert ctx.is_youtube_active() is True

    # Step 2: Search songs (in YouTube context -> routes to youtube, not web_search)
    cmd2 = "search songs"
    i2 = router.route(cmd2, context=ctx)
    assert i2.name == "youtube"
    assert i2.args == {"query": "songs", "play": False}
    reply2 = executor.execute(i2)
    assert "songs" in reply2.lower()
    ctx.update_search("songs", site="youtube")
    assert ctx.last_query == "songs"

    # Step 3: Search Arijit Singh romantic songs (preserves complete multi-word query)
    cmd3 = "search Arijit Singh romantic songs"
    i3 = router.route(cmd3, context=ctx)
    assert i3.name == "youtube"
    assert i3.args["query"] == "Arijit Singh romantic songs"
    assert i3.args["play"] is False
    reply3 = executor.execute(i3)
    assert "Arijit Singh romantic songs" in reply3
    ctx.update_search("Arijit Singh romantic songs", site="youtube")

    # Step 4: Click the first video
    cmd4 = "click the first video"
    i4 = router.route(cmd4, context=ctx)
    assert i4.name == "browser_click_video"
    assert i4.args.get("index", 1) == 1
    reply4 = executor.execute(i4)
    assert "first video" in reply4.lower()
    ctx.page_state = "watch"

    # Step 5: Pause playback
    cmd5 = "pause"
    i5 = router.route(cmd5, context=ctx)
    assert i5.name == "media_pause"
    reply5 = executor.execute(i5)
    assert "paused" in reply5.lower()
    ctx.update_media_state("paused")
    assert ctx.page_state == "paused"

    # Step 6: Resume playback
    cmd6 = "resume"
    i6 = router.route(cmd6, context=ctx)
    assert i6.name == "media_resume"
    reply6 = executor.execute(i6)
    assert "resumed" in reply6.lower()
    ctx.update_media_state("playing")
    assert ctx.page_state == "playing"

    # Step 7: Scroll down
    cmd7 = "scroll down"
    i7 = router.route(cmd7, context=ctx)
    assert i7.name == "scroll"
    assert i7.args["direction"] == "down"
    reply7 = executor.execute(i7)
    assert "scrolling down" in reply7.lower()

    # Step 8: Open the second video (ordinal targeting)
    cmd8 = "open the second video"
    i8 = router.route(cmd8, context=ctx)
    assert i8.name == "browser_click_video"
    assert i8.args["index"] == 2
    reply8 = executor.execute(i8)
    assert "second video" in reply8.lower()


# ---------------------------------------------------------------------------
# 13. Intent Disambiguation & Explicit Target Overrides
# ---------------------------------------------------------------------------
def test_intent_disambiguation_rules(router):
    # Case A: YouTube context active
    yt_ctx = ConversationContext()
    yt_ctx.update_site("youtube", "https://www.youtube.com")

    # 'search songs' uses active YouTube context
    i = router.route("search songs", context=yt_ctx)
    assert i.name == "youtube"
    assert i.args["query"] == "songs"
    assert i.args["play"] is False

    # 'search google for songs' explicitly overrides context to use Google
    i = router.route("search google for songs", context=yt_ctx)
    assert i.name == "web_search"
    assert i.args["query"] == "songs"

    # 'search for python tutorial on google'
    i = router.route("search for python tutorial on google", context=yt_ctx)
    assert i.name == "web_search"
    assert i.args["query"] == "python tutorial"

    # Case B: No active website context
    blank_ctx = ConversationContext()

    # 'search songs' with no context defaults to web search
    i = router.route("search songs", context=blank_ctx)
    assert i.name == "web_search"
    assert i.args["query"] == "songs"

    # 'search youtube for songs' explicitly uses YouTube
    i = router.route("search youtube for songs", context=blank_ctx)
    assert i.name == "youtube"
    assert i.args["query"] == "songs"
    assert i.args["play"] is False

    # 'play Arijit Singh romantic songs' has play=True
    i = router.route("play Arijit Singh romantic songs", context=blank_ctx)
    assert i.name == "youtube"
    assert i.args["query"] == "Arijit Singh romantic songs"
    assert i.args["play"] is True


# ---------------------------------------------------------------------------
# 14. Query Extraction Without Dropping Words
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cmd,expected_query", [
    ("search songs", "songs"),
    ("search Arijit Singh romantic songs", "Arijit Singh romantic songs"),
    ("search for machine learning tutorial 2026", "machine learning tutorial 2026"),
    ("find best python libraries for desktop automation", "best python libraries for desktop automation"),
    ("find lofi beats to relax", "lofi beats to relax"),
])
def test_query_extraction_preserves_all_words(router, cmd, expected_query):
    ctx = ConversationContext()
    ctx.update_site("youtube", "https://www.youtube.com")
    intent = router.route(cmd, context=ctx)
    assert intent.name == "youtube"
    assert intent.args["query"] == expected_query


# ---------------------------------------------------------------------------
# 15. Hindi and Hinglish Follow-Up & Ordinals
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cmd,expected_name,expected_args", [
    ("pehla video kholo", "browser_click_video", {"index": 1}),
    ("doosra video kholo", "browser_click_video", {"index": 2}),
    ("teesra video kholo", "browser_click_video", {"index": 3}),
    ("chautha video kholo", "browser_click_video", {"index": 4}),
    ("panchwa video kholo", "browser_click_video", {"index": 5}),
    ("open the 2nd video", "browser_click_video", {"index": 2}),
    ("click 3rd video", "browser_click_video", {"index": 3}),
    ("ruko", "media_pause", {}),
    ("rok do", "media_pause", {}),
    ("chalu karo", "media_resume", {}),
    ("resume karo", "media_resume", {}),
])
def test_hindi_hinglish_follow_ups(router, cmd, expected_name, expected_args):
    intent = router.route(cmd)
    assert intent.name == expected_name
    for k, v in expected_args.items():
        assert intent.args.get(k) == v


# ---------------------------------------------------------------------------
# 16. Context Lifecycle & Application Switching
# ---------------------------------------------------------------------------
def test_context_switching_resets_site(router):
    ctx = ConversationContext()
    ctx.update_site("youtube", "https://www.youtube.com")
    assert ctx.is_youtube_active() is True

    # Switching to desktop calculator clears website context
    ctx.update_app("calculator")
    assert ctx.is_youtube_active() is False
    assert ctx.target_app == "calculator"

    # Subsequent generic search now routes to web search, not YouTube
    intent = router.route("search songs", context=ctx)
    assert intent.name == "web_search"
    assert intent.args["query"] == "songs"


# ---------------------------------------------------------------------------
# 17. Duplicate Submission Prevention
# ---------------------------------------------------------------------------
def test_duplicate_submission_detection():
    ctx = ConversationContext()

    # First submission
    assert ctx.is_duplicate_submission("search songs", window_sec=1.0) is False

    # Rapid repetition within window
    assert ctx.is_duplicate_submission("search songs", window_sec=1.0) is True

    # Different command
    assert ctx.is_duplicate_submission("pause", window_sec=1.0) is False

    # After window expiration
    time.sleep(1.05)
    assert ctx.is_duplicate_submission("search songs", window_sec=1.0) is False


# ---------------------------------------------------------------------------
# 18. Browser Media Controls and Consent Dismissal
# ---------------------------------------------------------------------------
def test_browser_media_and_consent():
    ctx = ConversationContext()
    browser = BrowserAutomation(context=ctx)
    browser.input.press_keys = MagicMock(return_value=(True, "Pressed k."))
    browser.input.click_coordinate = MagicMock(return_value=(True, "Clicked."))

    # Pause media
    ok, msg = browser.pause_media()
    assert ok is True
    assert "paused" in msg.lower()
    browser.input.press_keys.assert_called_with(["k"])
    assert ctx.page_state == "paused"

    # Resume media
    ok, msg = browser.resume_media()
    assert ok is True
    assert "resumed" in msg.lower()
    assert ctx.page_state == "playing"

    # Dismiss consent dialog
    browser.perception.is_ocr_available = MagicMock(return_value=True)
    browser.perception.find_target = MagicMock(return_value=ScreenElement(
        text="Accept all", x=500, y=600, width=120, height=40, confidence=0.9
    ))
    dismissed = browser.dismiss_consent_dialog()
    assert dismissed is True
    browser.input.click_coordinate.assert_called_with(500, 600)


# ---------------------------------------------------------------------------
# 19. Text Editor Launching & Linux Resolution
# ---------------------------------------------------------------------------
def test_editor_launch_aliases_resolve_to_notepad(router):
    for phrase in ("open notepad", "open text editor", "open a new document", "open document"):
        intent = router.route(phrase)
        assert intent.name == "open", f"Phrase {phrase!r} did not route to open"
        assert intent.args["target"] == "notepad", f"Phrase {phrase!r} target was {intent.args['target']}"
        assert intent.args["kind"] == "app"


def test_compound_open_and_type_routing(router):
    for phrase in (
        "open notepad and type hello",
        "open text editor and type hello world",
        "open a new document and write welcome to maruti",
    ):
        intent = router.route(phrase)
        assert intent.name == "open_and_type"
        assert intent.args["app"] == "notepad"
        assert len(intent.args["text"]) > 0


# ---------------------------------------------------------------------------
# 20. Dictation vs. Editing Command Disambiguation
# ---------------------------------------------------------------------------
def test_dictation_disambiguation(router):
    # Dictation commands with words that look like editing actions
    intent_type_copy = router.route("type copy")
    assert intent_type_copy.name == "type_text"
    assert intent_type_copy.args["text"] == "copy"

    intent_write_select = router.route("write select all")
    assert intent_write_select.name == "type_text"
    assert intent_write_select.args["text"] == "select all"

    intent_type_open = router.route("type open notepad")
    assert intent_type_open.name == "type_text"
    assert intent_type_open.args["text"] == "open notepad"

    # Multi-line dictation
    intent_next_line = router.route("type this on the next line: My name is Joyson.")
    assert intent_next_line.name == "type_text"
    assert "My name is Joyson" in intent_next_line.args["text"]
    assert intent_next_line.args.get("newline") is True

    # Standalone editing commands (not dictation)
    assert router.route("copy").name in ("clipboard_copy", "press_keys")
    assert router.route("cut").name in ("clipboard_cut", "press_keys")
    assert router.route("paste").name in ("clipboard_paste", "press_keys")
    assert router.route("undo").name in ("edit_undo", "press_keys")
    assert router.route("redo").name in ("edit_redo", "press_keys")


# ---------------------------------------------------------------------------
# 21. Keyboard Shortcut Mappings & Linux GNOME Redo
# ---------------------------------------------------------------------------
def test_keyboard_shortcut_mappings():
    inp = DesktopInputBackend()
    assert inp.get_redo_shortcut() == ["ctrl", "shift", "z"] if inp.system == "Linux" else ["ctrl", "y"]

    with patch.object(inp.pg, "hotkey") as mock_hotkey, patch.object(inp.pg, "press") as mock_press:
        inp.select_all()
        mock_hotkey.assert_called_with("ctrl", "a")

        inp.clipboard_copy()
        mock_hotkey.assert_called_with("ctrl", "c")

        inp.clipboard_cut()
        mock_hotkey.assert_called_with("ctrl", "x")

        inp.clipboard_paste()
        mock_hotkey.assert_called_with("ctrl", "v")

        inp.edit_undo()
        mock_hotkey.assert_called_with("ctrl", "z")

        inp.save_file()
        mock_hotkey.assert_called_with("ctrl", "s")

        inp.clear_selection()
        mock_press.assert_called_with("right")


# ---------------------------------------------------------------------------
# 22. Line & Word Selection, Multi-Line & Empty Documents
# ---------------------------------------------------------------------------
def test_line_selection_logic(router):
    # Routing line selections
    assert router.route("select line one").args.get("line_number") == 1
    assert router.route("select line two").args.get("line_number") == 2
    assert router.route("select line 5").args.get("line_number") == 5
    assert router.route("select the current line").args.get("line_number") is None
    assert router.route("select line").args.get("line_number") is None

    # Context buffer tracking
    ctx = ConversationContext()
    ex = ActionExecutor(dry_run=True, context=ctx)

    # Empty document selection
    res_empty = ex.do_select_line(1)
    assert "empty" in res_empty.lower() or ctx.selected_text == ""

    # Populate document with 2 lines
    ctx.record_text_input("First line", newline=False)
    ctx.record_newline()
    ctx.record_text_input("Second line", newline=False)
    assert len(ctx.editor_buffer) == 2

    # Select line 1
    ex.do_select_line(1)
    assert ctx.selected_text == "First line"

    # Select line 2
    ex.do_select_line(2)
    assert ctx.selected_text == "Second line"

    # Select line 10 on a 2-line document
    res_overflow = ex.do_select_line(10)
    assert "2 lines" in res_overflow or "cannot select" in res_overflow


# ---------------------------------------------------------------------------
# 23. Sequential Execution: Exact 14-Step Acceptance Workflow
# ---------------------------------------------------------------------------
def test_acceptance_workflow_14_steps(router):
    """Verify the exact sequence of 14 commands from the acceptance test specification.

    1. 'Open Notepad.'
    2. 'Type hello.'
    3. 'Press Enter.'
    4. 'Type world.'
    5. 'Select line one.'
    6. 'Copy.'
    7. 'Go to the end of the document.'
    8. 'Press Enter.'
    9. 'Paste.'
    10. 'Undo.'
    11. 'Redo.'
    12. 'Select all.'
    13. 'Cut.'
    14. 'Paste.'
    """
    ctx = ConversationContext()
    ex = ActionExecutor(dry_run=True, context=ctx)

    # 1. 'Open Notepad.'
    i1 = router.route("Open Notepad.", context=ctx)
    r1 = ex.execute(i1)
    assert ctx.active_editor == "gnome-text-editor"
    assert "opening" in r1.lower()

    # 2. 'Type hello.'
    i2 = router.route("Type hello.", context=ctx)
    assert i2.name == "type_text"
    assert i2.args["text"] == "hello"
    ex.execute(i2)
    assert ctx.editor_buffer == ["hello"]
    assert ctx.get_document_text() == "hello"

    # 3. 'Press Enter.'
    i3 = router.route("Press Enter.", context=ctx)
    ex.execute(i3)
    assert len(ctx.editor_buffer) == 2
    assert ctx.editor_buffer[0] == "hello"

    # 4. 'Type world.'
    i4 = router.route("Type world.", context=ctx)
    assert i4.args["text"] == "world"
    ex.execute(i4)
    assert ctx.editor_buffer == ["hello", "world"]
    assert ctx.get_document_text() == "hello\nworld"

    # 5. 'Select line one.'
    i5 = router.route("Select line one.", context=ctx)
    assert i5.args.get("line_number") == 1
    ex.execute(i5)
    assert ctx.selected_text == "hello"

    # 6. 'Copy.'
    i6 = router.route("Copy.", context=ctx)
    ex.execute(i6)
    assert ctx.clipboard_content == "hello"

    # 7. 'Go to the end of the document.'
    i7 = router.route("Go to the end of the document.", context=ctx)
    ex.execute(i7)
    assert ctx.cursor_line == 1
    assert ctx.cursor_col == 5  # len('world')

    # 8. 'Press Enter.'
    i8 = router.route("Press Enter.", context=ctx)
    ex.execute(i8)
    assert len(ctx.editor_buffer) == 3

    # 9. 'Paste.'
    i9 = router.route("Paste.", context=ctx)
    ex.execute(i9)
    assert ctx.editor_buffer == ["hello", "world", "hello"]
    assert ctx.get_document_text() == "hello\nworld\nhello"

    # 10. 'Undo.'
    i10 = router.route("Undo.", context=ctx)
    ex.execute(i10)
    assert ctx.editor_buffer == ["hello", "world", ""]
    assert ctx.get_document_text() == "hello\nworld\n"

    # 11. 'Redo.'
    i11 = router.route("Redo.", context=ctx)
    ex.execute(i11)
    assert ctx.editor_buffer == ["hello", "world", "hello"]
    assert ctx.get_document_text() == "hello\nworld\nhello"

    # 12. 'Select all.'
    i12 = router.route("Select all.", context=ctx)
    ex.execute(i12)
    assert ctx.selected_text == "hello\nworld\nhello"

    # 13. 'Cut.'
    i13 = router.route("Cut.", context=ctx)
    ex.execute(i13)
    assert ctx.editor_buffer == [""]
    assert ctx.get_document_text() == ""
    assert ctx.clipboard_content == "hello\nworld\nhello"

    # 14. 'Paste.'
    i14 = router.route("Paste.", context=ctx)
    ex.execute(i14)
    assert ctx.editor_buffer == ["hello\nworld\nhello"]
    assert ctx.get_document_text() == "hello\nworld\nhello"


# ---------------------------------------------------------------------------
# 24. Wayland Backend Detection & Input Failure Handling
# ---------------------------------------------------------------------------
def test_wayland_backend_detection():
    inp = DesktopInputBackend()
    assert isinstance(inp.is_wayland, bool)
    assert inp.system in ("Linux", "Windows", "Darwin")


def test_input_failure_handling():
    inp = DesktopInputBackend()
    with patch.object(inp.pg, "write", side_effect=RuntimeError("Wayland injection denied")):
        ok, msg = inp.type_text("test")
        assert ok is False
        assert "failed" in msg.lower()


# ---------------------------------------------------------------------------
# 25. Clipboard Failure & Cancellation Handling
# ---------------------------------------------------------------------------
def test_clipboard_failure_graceful_handling():
    ctx = ConversationContext()
    ex = ActionExecutor(dry_run=False, context=ctx)
    with patch("pyperclip.paste", side_effect=Exception("Clipboard unavailable")):
        with patch.object(ex.registry.input, "clipboard_paste", return_value=(True, "Pasted.")):
            # Should not raise exception
            res = ex.do_clipboard_paste()
            assert "pasted" in res.lower()


def test_cancel_command_handling(router):
    intent = router.route("cancel")
    assert intent.name == "cancel"
    intent_stop = router.route("cancel action")
    assert intent_stop.name == "cancel"


def test_core_clipboard_operations():
    from core.clipboard import get_clipboard_text, set_clipboard_text
    ok = set_clipboard_text("MARUTI Wayland Test 42")
    assert ok is True
    assert get_clipboard_text() == "MARUTI Wayland Test 42"


def test_gui_action_worker_and_cleanup():
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from gui.app import ActionWorker
    from voice.tts import Speaker

    ctx = ConversationContext()
    ctx.editor_buffer = ["line 1", "line 2"]
    ex = ActionExecutor(dry_run=True, context=ctx)
    router = IntentRouter()
    speaker = Speaker(enabled=False)

    worker = ActionWorker(ex, router, speaker, "select line one", context=ctx)
    received = []
    worker.finished_signal.connect(lambda raw, reply, ok: received.append((raw, reply, ok)))
    worker.run()

    assert len(received) == 1
    raw, reply, ok = received[0]
    assert ok is True
    assert ctx.selected_text == "line 1"
    worker.deleteLater()



