from dataclasses import dataclass, field
@dataclass
class ScreenState:
    active_application: str = ""
    active_window: str = ""
    ui_elements: list = field(default_factory=list)
    visual_candidates: list = field(default_factory=list)
    screenshot: object = None
    screen_width: int = 0
    screen_height: int = 0
    ocr_elements: list = field(default_factory=list)
