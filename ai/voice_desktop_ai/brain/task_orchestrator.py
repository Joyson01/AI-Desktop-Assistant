from dataclasses import asdict, dataclass, field

from brain.screen_context import BrainInput, ScreenContext
from computer.action_pipeline import ActionPipeline
from verification.verifier import VerificationResult, verify_action


@dataclass
class TaskState:
    original_goal: str
    current_step: int = 0
    action_history: list = field(default_factory=list)
    screenshot_history: list = field(default_factory=list)
    last_action: dict | None = None
    last_result: dict | None = None
    expected_state: object = None
    status: str = "running"
    message: str = ""

    def to_dict(self):
        return asdict(self)


class TaskOrchestrator:
    def __init__(self, brain, executor, observe, verifier=None, max_retries=2, max_steps=20):
        self.brain = brain
        self.pipeline = ActionPipeline(brain, executor)
        self.observe = observe
        self.verifier = verifier or self._default_verifier
        self.max_retries = max(0, max_retries)
        self.max_steps = max(1, max_steps)

    def run(self, goal, context=None, history=None):
        state = TaskState(original_goal=str(goal))
        screen = ScreenContext.from_observation(self.observe())
        self._record_screenshot(state, screen)
        retries = 0
        action_history = list(history or [])

        while state.status == "running":
            if state.current_step >= self.max_steps:
                return self._fail(state, "Maximum task steps reached.")

            state.current_step += 1
            brain_context = dict(context or {})
            brain_context["task_state"] = state.to_dict()
            try:
                brain_input = BrainInput(
                    goal=state.original_goal,
                    screen=screen,
                    action_history=tuple(action_history),
                    last_action=state.last_action,
                    last_verification=(state.last_result or {}).get(
                        "verification_result", (state.last_result or {}).get("verification")
                    ),
                    task_step=state.current_step,
                    context=brain_context,
                )
                brain_result = self.brain.analyze(brain_input)
                action = brain_result.action
            except (AttributeError, TypeError, ValueError) as error:
                return self._fail(state, str(error))

            state.last_action = action.to_dict()
            state.expected_state = getattr(brain_result, "expected_state", None)
            if action.name == "ask_user":
                state.status = "waiting_for_user"
                state.message = action.message
                return state
            if action.name == "done":
                state.status = "completed"
                state.message = action.message
                return state

            result = self.pipeline.execute_result(
                brain_result,
                screen.screenshot,
                {**brain_context, **screen.to_metadata()},
            )
            state.last_result = result
            state.action_history.append({"action": state.last_action, "result": result})
            action_history.append(state.last_action)
            next_screen = ScreenContext.from_observation(self.observe())
            self._record_screenshot(state, next_screen)
            verification = (
                VerificationResult("failure", 1.0, result.get("message", "Action failed."))
                if not result.get("success")
                else self._verification_result(
                    screen, next_screen, state.last_action, result, state
                )
            )
            result["verification"] = verification.status
            result["verification_result"] = verification.to_dict()
            if result.get("stage") == "validation":
                return self._fail(state, result["message"])
            if result.get("success") and verification.status in {"success", "uncertain"}:
                retries = 0
                screen = next_screen
                continue

            retries += 1
            if retries > self.max_retries:
                return self._fail(state, result.get("message", "Action could not be verified."))
            screen = next_screen

        return state

    def _verification_result(self, before, after, action, result, state):
        verification = self.verifier(before, after, action, result, state)
        if isinstance(verification, VerificationResult):
            return verification
        if verification is True:
            return VerificationResult("success", 1.0, "Verifier accepted the transition.")
        if verification is False:
            return VerificationResult("failure", 1.0, "Verifier rejected the transition.")
        if verification in {"success", "failure", "uncertain"}:
            return VerificationResult(verification)
        return VerificationResult("uncertain", 0.0, "Verifier could not determine the outcome.")

    @staticmethod
    def _default_verifier(before, after, action, result, state):
        if verify_action(lambda: after, before):
            return VerificationResult("success", 1.0, "Observed state is valid.")
        return VerificationResult("uncertain", 0.0, "Observed state could not be confirmed.")

    @staticmethod
    def _record_screenshot(state, screen):
        size = (screen.width, screen.height)
        state.screenshot_history.append({"index": len(state.screenshot_history), "size": size})

    @staticmethod
    def _fail(state, message):
        state.status = "failed"
        state.message = message
        return state