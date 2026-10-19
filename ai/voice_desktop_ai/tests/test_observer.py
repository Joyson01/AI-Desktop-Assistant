from PIL import Image

from perception import observer


def test_observe_screen_includes_screenshot_dimensions(monkeypatch):
    image = Image.new("RGB", (800, 600))
    monkeypatch.setattr(observer, "capture_screen", lambda: image)
    monkeypatch.setattr(observer, "observe", lambda: ("Chrome", []))

    state = observer.observe_screen(include_fallback=True)

    assert state.screenshot is image
    assert (state.screen_width, state.screen_height) == (800, 600)
    assert state.active_window == "Chrome"


def test_observe_screen_skips_screenshot_without_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(observer, "capture_screen", lambda: calls.append(True))
    monkeypatch.setattr(observer, "observe", lambda: ("Chrome", []))

    state = observer.observe_screen()

    assert state.screenshot is None
    assert calls == []