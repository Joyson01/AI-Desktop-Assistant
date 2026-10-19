from brain.intent_router import IntentRouter
from assistant import AccessibilityAssistant
from computer.app_launcher import resolve_application


router = IntentRouter()


def test_screenshot_and_caps_and_minimize_routes():
    normal = router.route("Take screenshot")
    assert normal.semantic_intent == "screenshot_start"
    assert normal.metadata == {"action": "screenshot_start"}
    assert router.route("Screenshot le lo").semantic_intent == "screenshot_start"
    full_screen_commands = (
        "take full screen",
        "take a full screen screenshot",
        "full screen screenshot",
        "capture full screen",
        "capture the whole screen",
        "capture entire screen",
        "take whole screen screenshot",
        "poori screen ka screenshot",
        "puri screen ka screenshot le lo",
        "poori screen capture karo",
    )
    for command in full_screen_commands:
        route = router.route(command)
        assert route.semantic_intent == "screenshot_start", command
        assert route.metadata == {"action": "take_screenshot", "mode": "full_screen"}, command


def test_full_screen_screenshot_bypasses_crop_ui_action():
    normal_action = AccessibilityAssistant._structured_action(router.route("take screenshot"))
    full_screen_action = AccessibilityAssistant._structured_action(router.route("take full screen"))

    assert normal_action == {"action": "screenshot_start"}
    assert full_screen_action == {"action": "take_screenshot", "mode": "full_screen"}
    assert router.route("Caps on karo").semantic_intent == "caps_lock"
    assert router.route("Caps lock off").semantic_intent == "caps_lock"
    assert router.route("Window minimize karo").semantic_intent == "minimize_window"
    assert router.route("minimise the window").semantic_intent == "minimize_window"
    assert router.route("minize window").semantic_intent == "minimize_window"
    assert router.route("Restore window").semantic_intent == "restore_window"
    assert router.route("File par right click karo").semantic_intent == "right_click"


def test_application_alias_resolution():
    explorer = resolve_application("file explorer")
    vscode = resolve_application("VS Code")
    edge = resolve_application("microsoft edge")
    word = resolve_application("word")
    notepad = resolve_application("notepad")

    assert explorer["canonical"] == "explorer"
    assert vscode["canonical"] == "vscode"
    assert edge["canonical"] == "edge"
    assert word["canonical"] == "word"
    assert notepad["canonical"] == "notepad"


def test_multiple_and_ambiguous_application_requests():
    routed = router.route("Open Chrome and Edge")
    assert routed.semantic_intent == "open_multiple_applications"
    assert routed.metadata["applications"] == ["chrome", "edge"]
    assert router.route("Open file").route == "ambiguous"
    assert router.route("Open code").route == "ambiguous"
    assert resolve_application("code")["found"] is False
