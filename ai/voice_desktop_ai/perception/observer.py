from perception.screen import ScreenState
from perception.uia import observe
from computer.screenshot import capture_screen
import time

def observe_screen(include_fallback=False, target=None):
    started = time.perf_counter()
    if target is None:
        title, elements = observe()
    else:
        try:
            title, elements = observe(target=target)
        except TypeError:
            title, elements = observe()
    print(f"[PERF] uia_lookup={(time.perf_counter() - started) * 1000:.1f}ms")
    screenshot = None
    if include_fallback:
        screenshot_started = time.perf_counter()
        try:
            screenshot = capture_screen()
        except Exception:
            pass
        print(f"[PERF] observe={(time.perf_counter() - screenshot_started) * 1000:.1f}ms")
    width, height = getattr(screenshot, "size", (0, 0)) if screenshot is not None else (0, 0)
    return ScreenState(
        active_application=title,
        active_window=title,
        ui_elements=elements,
        screenshot=screenshot,
        screen_width=width,
        screen_height=height,
    )
