from brain.task_orchestrator import TaskOrchestrator
from tests.fixtures.fake_executor import FakeExecutor
from tests.fixtures.fake_observer import FakeObserver
from tests.fixtures.screens import make_screen
from tests.fixtures.workflows import WorkflowBrain, WorkflowVerifier


def run_workflow(states, responses, expected_states, goal="fixture", executor=None):
    executor = executor or FakeExecutor()
    observer = FakeObserver([make_screen(state) for state in states])
    brain = WorkflowBrain(responses)
    verifier = WorkflowVerifier(expected_states)
    orchestrator = TaskOrchestrator(brain, executor, observer, verifier=verifier)
    return orchestrator.run(goal), executor, observer, brain, verifier


def test_open_chrome_workflow_is_verified():
    state, executor, observer, _, verifier = run_workflow(
        ["desktop", "chrome_open"],
        {"desktop": [{"action": "click", "x": 100, "y": 200}], "chrome_open": [{"action": "done", "message": "Chrome opened"}]},
        ["chrome_open"],
    )

    assert state.status == "completed"
    assert [call["action"] for call in executor.calls] == ["click"]
    assert verifier.calls[0]["after"] == "chrome_open"
    assert len(observer.calls) == 2


def test_open_chrome_and_search_youtube_is_many_verified_actions():
    state, executor, _, _, _ = run_workflow(
        ["desktop", "chrome_open", "search_box", "search_results"],
        {
            "desktop": [{"action": "click", "x": 100, "y": 200}],
            "chrome_open": [{"action": "click", "x": 300, "y": 250}],
            "search_box": [{"action": "type", "text": "YouTube"}],
            "search_results": [{"action": "press", "key": "enter"}, {"action": "done", "message": "YouTube opened"}],
        },
        ["chrome_open", "search_box", "search_results", "search_results"],
    )

    assert state.status == "completed"
    assert [call["action"] for call in executor.calls] == ["click", "click", "type", "press"]


def test_full_account_search_and_play_workflow_is_not_one_giant_action():
    states = ["desktop", "chrome_open", "account_page", "youtube_open", "search_box", "search_results", "video_page", "playing"]
    responses = {
        "desktop": [{"action": "click", "x": 100, "y": 200}],
        "chrome_open": [{"action": "click", "x": 300, "y": 250}],
        "account_page": [{"action": "click", "x": 400, "y": 300}],
        "youtube_open": [{"action": "click", "x": 500, "y": 350}],
        "search_box": [{"action": "type", "text": "YouTube"}],
        "search_results": [{"action": "press", "key": "enter"}],
        "video_page": [{"action": "click", "x": 700, "y": 400}],
        "playing": [{"action": "done", "message": "Saiyaara is playing"}],
    }
    state, executor, _, _, verifier = run_workflow(states, responses, states[1:])

    assert state.status == "completed"
    assert len(executor.calls) == 7
    assert len(verifier.calls) == 7
    assert all("code" not in call for call in executor.calls)


def test_enter_button_target_is_distinct_from_unrelated_text():
    observer = FakeObserver([make_screen("editor", visible=("File", "Help", "Enter button")), make_screen("submitted")])
    brain = WorkflowBrain({"editor": [{"action": "click", "x": 200, "y": 100}], "submitted": [{"action": "done", "message": "Submitted"}]})
    executor = FakeExecutor()
    state = TaskOrchestrator(brain, executor, observer, verifier=WorkflowVerifier(["submitted"])).run("Click the Enter button")

    assert state.status == "completed"
    assert executor.calls == [{"action": "click", "target": {"x": 200, "y": 100}}]


def test_ctrl_r_then_enter_workflow():
    state, executor, _, _, _ = run_workflow(
        ["page", "reloaded", "submitted"],
        {"page": [{"action": "hotkey", "keys": ["ctrl", "r"]}], "reloaded": [{"action": "press", "key": "enter"}], "submitted": [{"action": "done", "message": "Done"}]},
        ["reloaded", "submitted"],
    )

    assert state.status == "completed"
    assert executor.calls == [
        {"action": "hotkey", "keys": ["ctrl", "r"]},
        {"action": "press", "key": "enter"},
    ]


def test_scroll_then_click_video_workflow():
    state, executor, _, _, _ = run_workflow(
        ["results", "scrolled_results", "video_page"],
        {"results": [{"action": "scroll", "amount": -600}], "scrolled_results": [{"action": "click", "x": 600, "y": 500}], "video_page": [{"action": "done", "message": "Video opened"}]},
        ["scrolled_results", "video_page"],
    )

    assert state.status == "completed"
    assert [call["action"] for call in executor.calls] == ["scroll", "click"]


def test_ambiguous_youtube_target_stops_without_execution():
    state, executor, _, _, _ = run_workflow(
        ["launcher"],
        {"launcher": [{"action": "ask_user", "message": "Which one: YouTube, YouTube Music, or YouTube Studio?"}]},
        [],
    )

    assert state.status == "waiting_for_user"
    assert executor.calls == []


def test_target_not_found_stops_without_fake_success():
    state, executor, _, _, _ = run_workflow(
        ["settings"],
        {"settings": [{"action": "ask_user", "message": "I cannot find Bluetooth."}]},
        [],
    )

    assert state.status == "waiting_for_user"
    assert executor.calls == []


def test_verification_failure_reanalyzes_then_recovers():
    state, executor, _, brain, verifier = run_workflow(
        ["search_results", "search_results", "playing"],
        {"search_results": [
            {"action": "click", "x": 700, "y": 400},
            {"action": "click", "x": 720, "y": 420},
        ], "playing": [{"action": "done", "message": "Playing"}]},
        ["playing", "playing"],
    )

    assert state.status == "completed"
    assert len(executor.calls) == 2
    assert verifier.calls[0]["after"] == "search_results"
    assert brain.inputs[1].last_verification["status"] == "failure"


def test_play_verification_success_and_screenshot_history_are_recorded():
    state, executor, observer, brain, verifier = run_workflow(
        ["video_page", "playing"],
        {"video_page": [{"action": "click", "x": 700, "y": 400}], "playing": [{"action": "done", "message": "Playing"}]},
        ["playing"],
    )

    assert state.status == "completed"
    assert state.action_history[0]["result"]["verification_result"]["status"] == "success"
    assert brain.inputs[1].screen.screenshot != brain.inputs[0].screen.screenshot
    assert len(observer.calls) == 2