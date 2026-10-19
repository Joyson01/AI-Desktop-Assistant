from dataclasses import dataclass

from brain.screen_context import ScreenContext


@dataclass(frozen=True)
class FakeScreenshot:
    label: str
    size: tuple = (1920, 1080)


def make_screen(state, visible=(), ocr_text=(), active_application=""):
    return ScreenContext(
        screenshot=FakeScreenshot(state),
        active_application=active_application or state,
        active_window=state,
        state=state,
        ocr_text=tuple(ocr_text),
        uia_metadata=tuple(visible),
    )