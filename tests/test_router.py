"""Test suite for MARUTI intent router and action executor.

Tests cover:
- Basic intent names for English, Hindi and Hinglish input
- Argument extraction correctness
- YouTube-specific routing (search vs. open)
- Web search query cleaning
- Exit phrase handling
- Fuzzy matching thresholds
- Dry-run action execution (no actual side-effects)
"""
import pytest
from intent_router import IntentRouter, parse_keys
from actions import ActionExecutor
from brain import Brain

r = IntentRouter()


# ---------------------------------------------------------------------------
# Intent name routing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,name", [
    # Greetings
    ("Hello maruti", "greet"),
    ("namaste", "greet"),
    # App opens
    ("maruti open chrome", "open"),
    ("launch chrome", "open"),
    ("start google chrome", "open"),
    ("chrome kholo", "open"),
    ("open settings", "open"),
    ("open google.com", "open"),
    ("open notepad", "open"),
    ("open calculator", "open"),
    ("open file explorer", "open"),
    # Sites
    ("open youtube", "open"),
    ("open google", "open"),
    # Hello world coding task
    ("write a simple hello world code", "hello_world"),
    # Keyboard shortcuts
    ("select all", "press_keys"),
    # Scroll
    ("neeche scroll karo", "scroll"),
    ("scroll up", "scroll"),
    # Navigation
    ("go back", "nav"),
    # Tabs/windows
    ("open new tab", "new_tab"),
    ("close tab", "close_tab"),
    ("minimize the window", "minimize"),
    ("close the window", "close_window"),
    ("switch the window", "switch_window"),
    # Caps lock
    ("caps on", "caps"),
    # YouTube
    ("play saiyara song", "youtube"),
    ("search youtube for python tutorials", "youtube"),
    ("search youtube for lofi music", "youtube"),
    ("search lofi beats on youtube", "youtube"),
    # Web search
    ("search for machine learning", "web_search"),
    ("search google for machine learning", "web_search"),
    # Chat
    ("who is the current pm in india", "chat"),
    ("who is owner of tesla", "chat"),
    # Vision click
    ("click on login", "click"),
    # Exit commands
    ("exit", "exit"),
    ("stop listening", "exit"),
    ("exit assistant", "exit"),
    ("quit assistant", "exit"),
])
def test_names(text, name):
    result = r.route(text)
    assert result.name == name, (
        f"Expected '{name}' for {text!r}, got '{result.name}' "
        f"(args={result.args}, conf={result.confidence})"
    )


# ---------------------------------------------------------------------------
# Argument extraction
# ---------------------------------------------------------------------------
def test_args():
    assert r.route("type Hello World").args["text"] == "Hello World"
    assert r.route("press ctrl a").args["keys"] == ["ctrl", "a"]
    assert r.route("press shift 1").args["keys"] == ["shift", "1"]
    assert r.route("press ctrl + 2").args["keys"] == ["ctrl", "2"]
    assert r.route("scroll down").args == {"direction": "down", "amount": 500}
    assert r.route("caps lock off").args["state"] == "off"

    w = r.route("what is the current weather of boisar")
    assert w.name == "weather" and w.args["city"] == "boisar"

    y = r.route("YouTube pe lofi beats search karo")
    assert y.args == {"query": "lofi beats", "play": False}


# ---------------------------------------------------------------------------
# YouTube query extraction — query must NOT include "youtube for"
# ---------------------------------------------------------------------------
def test_youtube_query_extraction():
    y1 = r.route("search youtube for python tutorials")
    assert y1.name == "youtube", f"Got {y1.name}"
    assert "youtube" not in y1.args["query"].lower(), (
        f"Query contains 'youtube': {y1.args['query']!r}"
    )
    assert "for" not in y1.args["query"].lower() or y1.args["query"].lower() != "for python tutorials", (
        f"Query starts with 'for': {y1.args['query']!r}"
    )
    assert "python tutorials" in y1.args["query"].lower(), (
        f"Expected 'python tutorials' in query, got: {y1.args['query']!r}"
    )

    y2 = r.route("search lofi music on youtube")
    assert y2.name == "youtube"
    assert "lofi music" in y2.args["query"].lower()


# ---------------------------------------------------------------------------
# Web search query cleaning — must NOT include "google for"
# ---------------------------------------------------------------------------
def test_web_search_query_cleaning():
    ws = r.route("search google for machine learning")
    assert ws.name == "web_search"
    assert "google" not in ws.args["query"].lower(), (
        f"Query still contains 'google': {ws.args['query']!r}"
    )
    assert "machine learning" in ws.args["query"].lower(), (
        f"Expected 'machine learning' in query, got: {ws.args['query']!r}"
    )


# ---------------------------------------------------------------------------
# Exit phrase variations
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "exit", "quit", "bye", "goodbye",
    "stop listening", "exit assistant", "quit assistant",
    "stop assistant",
])
def test_exit_phrases_route_to_exit(phrase):
    assert r.route(phrase).name == "exit", f"Expected exit for {phrase!r}, got {r.route(phrase).name}"


# ---------------------------------------------------------------------------
# Invalid key sequences
# ---------------------------------------------------------------------------
def test_invalid_keys():
    assert parse_keys("ctrl a v c") is None
    assert r.route("press banana").name == "unknown"


# ---------------------------------------------------------------------------
# Fuzzy matching thresholds
# ---------------------------------------------------------------------------
def test_fuzzy_act_ask_reject():
    act = r.route("open notepat")
    assert act.name == "open" and act.args["label"] == "notepad" and act.confidence >= 0.85
    assert r.route("open qzxv").name == "unknown"


# ---------------------------------------------------------------------------
# Wake word detection
# ---------------------------------------------------------------------------
def test_wake_word():
    assert r.has_wake("hello maruti open chrome")
    assert not r.has_wake("open chrome")


# ---------------------------------------------------------------------------
# Dry-run action execution (no real side effects)
# ---------------------------------------------------------------------------
def test_dry_run_has_no_side_effects():
    ex = ActionExecutor(Brain(), dry_run=True)
    # App open
    assert ex.execute(r.route("open chrome")) == "Opening chrome."
    # Typing
    assert ex.execute(r.route("type hello")) == "Typed."
    # Safety gate defaults to 'no' confirmation -> cancel
    assert ex.execute(r.route("close the window")) == "Okay, I did not close it."
    # Greeting
    assert "Maruti" in ex.execute(r.route("hello"))
    # YouTube search
    yt = r.route("search youtube for python tutorials")
    result = ex.execute(yt)
    assert "python tutorials" in result.lower(), f"Unexpected: {result!r}"


# ---------------------------------------------------------------------------
# NLU package import path
# ---------------------------------------------------------------------------
def test_nlu_package_import():
    from nlu.router import IntentRouter as NLURouter
    nr = NLURouter()
    assert nr.route("open chrome").name == "open"


def test_hindi_hinglish_command_routing():
    """Verify Hindi and Hinglish commands resolve to appropriate intents."""
    # App launch
    assert r.route("kholo calculator").name == "open"
    assert r.route("kholo notepad").name == "open"
    assert r.route("chrome kholo").name == "open"

    # Search with query payload preserved
    intent_search = r.route("dhoondo scholarship information")
    assert intent_search.name == "web_search"
    assert intent_search.args["query"] == "scholarship information"

    # Typing with literal payload preserved
    intent_type = r.route("likho namaste")
    assert intent_type.name == "type_text"
    assert intent_type.args["text"] == "namaste"


def test_payload_text_preservation():
    """Verify that casing, punctuation and spaces in typing and search queries are preserved."""
    res_type = r.route("type Hello, World! 123")
    assert res_type.name == "type_text"
    assert res_type.args["text"] == "Hello, World! 123"

    res_search = r.route("search Python tutorials on google")
    assert res_search.name == "web_search"
    assert "Python tutorials" in res_search.args["query"]


def test_scrolling_boundary_intents():
    """Verify scroll to top and bottom commands."""
    res_top = r.route("scroll to top")
    assert res_top.name == "scroll"
    assert res_top.args["direction"] == "up"
    assert res_top.args.get("boundary") == "top"

    res_bottom = r.route("scroll to bottom")
    assert res_bottom.name == "scroll"
    assert res_bottom.args["direction"] == "down"
    assert res_bottom.args.get("boundary") == "bottom"


def test_keyboard_actions_and_shortcuts():
    """Verify key shortcuts for Enter, Tab, Esc, Select All, Copy, Paste, Cut, Undo, Redo."""
    assert r.route("press enter").name == "press_keys"
    assert r.route("press enter").args["keys"] == ["enter"]

    assert r.route("press tab").name == "press_keys"
    assert r.route("press tab").args["keys"] == ["tab"]

    assert r.route("press escape").name == "press_keys"
    assert r.route("press escape").args["keys"] == ["esc"]

    assert r.route("new line").name == "press_keys"
    assert r.route("new line").args["keys"] == ["enter"]

    assert r.route("select all").name in ("press_keys", "select_all")
    assert r.route("copy").name in ("clipboard_copy", "press_keys")
    assert r.route("paste").name in ("clipboard_paste", "press_keys")
    assert r.route("cut").name in ("clipboard_cut", "press_keys")
    assert r.route("undo").name in ("edit_undo", "press_keys")
    assert r.route("redo").name in ("edit_redo", "press_keys")


def test_dictation_mode_lifecycle():
    """Verify start/stop dictation and literal transcription while dictating."""
    from core.context import ConversationContext
    ctx = ConversationContext()

    assert r.route("start dictation").name == "start_dictation"
    assert r.route("stop dictation").name == "stop_dictation"

    # When dictation mode is active in context
    ctx.is_dictation_mode = True
    # Normal commands should NOT execute as commands
    dictated = r.route("open chrome", context=ctx)
    assert dictated.name == "type_text"
    assert dictated.args["text"] == "open chrome"

    # Stop dictation must break out of dictation mode
    stop_intent = r.route("stop dictation", context=ctx)
    assert stop_intent.name == "stop_dictation"


def test_readme_command_examples():
    """Verify all command examples documented in README.md route accurately."""
    # App and folder launching
    res = r.route("open calculator")
    assert res.name == "open" and res.args["target"] == "calculator"

    res = r.route("open browser")
    assert res.name == "open" and res.args["target"] == "chrome"

    res = r.route("open firefox")
    assert res.name == "open" and res.args["target"] == "firefox"

    res = r.route("open files")
    assert res.name == "open" and res.args["target"] == "file explorer"

    res = r.route("open text editor")
    assert res.name == "open" and res.args["target"] == "notepad"

    res = r.route("open google.com")
    assert res.name == "open" and res.args["kind"] == "site" and res.args["target"] == "https://google.com"

    # Search commands
    res = r.route("search Python tutorials")
    assert res.name == "web_search" and res.args["query"] == "Python tutorials"

    res = r.route("search youtube keyboard shortcuts")
    assert res.name == "youtube" and res.args["query"] == "keyboard shortcuts" and res.args["play"] is False

    # Typing and dictation
    res = r.route("type hello")
    assert res.name == "type_text" and res.args["text"] == "hello"

    # Scrolling with repetition counts
    res_up = r.route("scroll up 3")
    assert res_up.name == "scroll" and res_up.args["direction"] == "up" and res_up.args["repetitions"] == 3

    res_down = r.route("scroll down 3")
    assert res_down.name == "scroll" and res_down.args["direction"] == "down" and res_down.args["repetitions"] == 3

    # Visual click
    res = r.route("click Sign in")
    assert res.name == "click" and res.args["label"] == "Sign in"

    # Control phrases
    res = r.route("cancel")
    assert res.name == "cancel"

    res = r.route("exit assistant")
    assert res.name == "exit"

    # Hinglish command examples
    res = r.route("kholo calculator")
    assert res.name == "open" and res.args["target"] == "calculator"

    res = r.route("dhoondo scholarship information")
    assert res.name == "web_search" and res.args["query"] == "scholarship information"

    res = r.route("likho namaste")
    assert res.name == "type_text" and res.args["text"] == "namaste"


