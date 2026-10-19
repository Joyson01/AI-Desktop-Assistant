from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ScreenContext:
    screenshot: object
    width: int = 0
    height: int = 0
    active_application: str = ""
    active_window: str = ""
    url: str = ""
    state: str = ""
    ocr_text: tuple = field(default_factory=tuple)
    uia_metadata: tuple = field(default_factory=tuple)

    def __post_init__(self):
        width, height = self.width, self.height
        if (not width or not height) and hasattr(self.screenshot, "size"):
            width, height = self.screenshot.size
            object.__setattr__(self, "width", width)
            object.__setattr__(self, "height", height)

    @classmethod
    def from_observation(cls, observation):
        if isinstance(observation, cls):
            return observation
        screenshot = getattr(observation, "screenshot", observation)
        return cls(
            screenshot=screenshot,
            width=getattr(observation, "screen_width", 0),
            height=getattr(observation, "screen_height", 0),
            active_application=getattr(observation, "active_application", ""),
            active_window=getattr(observation, "active_window", ""),
            state=getattr(observation, "state", ""),
            ocr_text=tuple(getattr(observation, "ocr_elements", ()) or ()),
            uia_metadata=tuple(getattr(observation, "ui_elements", ()) or ()),
        )

    def to_metadata(self):
        return {
            "width": self.width,
            "height": self.height,
            "active_application": self.active_application,
            "active_window": self.active_window,
            "url": self.url,
            "state": self.state,
            "ocr_text": list(self.ocr_text),
            "uia_metadata": list(self.uia_metadata),
        }


@dataclass(frozen=True)
class BrainInput:
    goal: str
    screen: ScreenContext
    action_history: tuple = field(default_factory=tuple)
    last_action: dict | None = None
    last_verification: object = None
    task_step: int = 0
    context: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "goal": self.goal,
            "screen": self.screen.to_metadata(),
            "action_history": list(self.action_history),
            "last_action": self.last_action,
            "last_verification": self.last_verification,
            "task_step": self.task_step,
            "context": dict(self.context),
        }