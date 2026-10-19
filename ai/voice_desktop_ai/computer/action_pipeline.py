from brain.visual_brain import VisualBrainResult
from computer.actions import ActionValidator, StructuredActionAdapter


class ActionPipeline:
    """Connect a visual brain to the existing controlled action executor."""

    def __init__(self, brain, executor):
        self.brain = brain
        self.adapter = StructuredActionAdapter(executor)

    def run(self, goal, screenshot, context=None, history=None):
        try:
            result = self.brain.analyze(goal, screenshot, context, history)
            if not isinstance(result, VisualBrainResult):
                result = VisualBrainResult.from_payload(result)
            return self.execute_result(result, screenshot, context)
        except (TypeError, ValueError) as error:
            return {"success": False, "message": str(error)}

    def execute_result(self, result, screenshot=None, context=None):
        try:
            if not isinstance(result, VisualBrainResult):
                result = VisualBrainResult.from_payload(result)
            screen_size = _screen_size(screenshot, context)
            valid, message = ActionValidator.validate(result.action.to_dict(), screen_size)
            if not valid:
                return {"success": False, "stage": "validation", "message": message}
            return self.adapter.execute(result.action.to_dict())
        except (TypeError, ValueError) as error:
            return {"success": False, "message": str(error)}


def _screen_size(screenshot, context):
    if screenshot is not None and hasattr(screenshot, "size"):
        return screenshot.size
    if isinstance(context, dict):
        width = context.get("screen_width")
        height = context.get("screen_height")
        if isinstance(width, int) and isinstance(height, int):
            return width, height
    return None