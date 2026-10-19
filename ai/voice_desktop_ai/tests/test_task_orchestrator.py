from PIL import Image

from brain.task_orchestrator import TaskOrchestrator
from brain.visual_brain import MockVisualBrain


class FakeExecutor:
    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    def execute(self, payload):
        self.calls.append(payload)
        return self.results.pop(0) if self.results else {"success": True, "message": "executed"}


def screenshots():
    return iter(Image.new("RGB", (1920, 1080), color) for color in ("red", "green", "blue", "white", "black"))


def make_orchestrator(responses, executor=None, verifier=None, max_retries=2, max_steps=20):
    executor = executor or FakeExecutor()
    brain = MockVisualBrain({"goal": responses})
    screen_iterator = screenshots()
    return (
        TaskOrchestrator(
            brain,
            executor,
            lambda: next(screen_iterator),
            verifier=verifier or (lambda before, after, action, result, state: "success"),
            max_retries=max_retries,
            max_steps=max_steps,
        ),
        executor,
        brain,
    )


def test_successful_multi_step_task_runs_one_action_per_iteration():
    orchestrator, executor, brain = make_orchestrator([
        {"action": "click", "x": 100, "y": 200},
        {"action": "type", "text": "Saiyaara"},
        {"action": "press", "key": "enter"},
        {"action": "done", "message": "Finished"},
    ])

    state = orchestrator.run("goal")

    assert state.status == "completed"
    assert [call["action"] for call in executor.calls] == ["click", "type", "press"]
    assert state.current_step == 4
    assert len(state.screenshot_history) == 4
    assert brain.last_request["screenshot"] is not None


def test_done_immediately_and_ask_user_do_not_execute():
    for response, status in (
        ({"action": "done", "message": "Already finished"}, "completed"),
        ({"action": "ask_user", "message": "Which account?"}, "waiting_for_user"),
    ):
        orchestrator, executor, _ = make_orchestrator([response])

        state = orchestrator.run("goal")

        assert state.status == status
        assert executor.calls == []


def test_invalid_action_and_out_of_screen_action_fail_without_execution():
    for response in (
        {"action": "run_python", "code": "print(1)"},
        {"action": "click", "x": 3000, "y": 500},
    ):
        orchestrator, executor, _ = make_orchestrator([response])

        state = orchestrator.run("goal")

        assert state.status == "failed"
        assert executor.calls == []


def test_executor_failure_is_reanalyzed_and_can_recover():
    executor = FakeExecutor([{"success": False, "message": "temporary failure"}, {"success": True}])
    orchestrator, executor, _ = make_orchestrator([
        {"action": "click", "x": 100, "y": 200},
        {"action": "type", "text": "recovered"},
        {"action": "done", "message": "Recovered"},
    ], executor=executor)

    state = orchestrator.run("goal")

    assert state.status == "completed"
    assert len(executor.calls) == 2
    assert state.action_history[0]["result"]["verification"] == "failure"


def test_verification_failure_retries_until_limit():
    orchestrator, executor, _ = make_orchestrator(
        [{"action": "click", "x": 100, "y": 200}] * 3,
        verifier=lambda before, after, action, result, state: "failure",
        max_retries=2,
    )

    state = orchestrator.run("goal")

    assert state.status == "failed"
    assert len(executor.calls) == 3


def test_max_steps_prevents_infinite_loop_and_preserves_history():
    orchestrator, executor, brain = make_orchestrator(
        [{"action": "scroll", "amount": -100}] * 5,
        max_steps=3,
    )

    state = orchestrator.run("goal")

    assert state.status == "failed"
    assert state.message == "Maximum task steps reached."
    assert state.current_step == 3
    assert len(state.action_history) == 3
    assert len(executor.calls) == 3
    assert brain.last_request["history"] == [entry["action"] for entry in state.action_history[:2]]