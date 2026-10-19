from PIL import Image

from computer import screenshot
from computer.action_executor import ActionExecutor


def test_capture_screen_returns_image_and_saves_debug_copy(monkeypatch, tmp_path):
    captured = {}
    image = Image.new("RGB", (4, 3), "white")

    def fake_grab(**kwargs):
        captured.update(kwargs)
        return image

    monkeypatch.setattr(screenshot.ImageGrab, "grab", fake_grab)

    output = screenshot.capture_screen(region=(1, 2, 5, 6), debug_path=tmp_path / "screen.png")

    assert output is image
    assert captured == {"bbox": (1, 2, 5, 6), "all_screens": True}
    assert (tmp_path / "screen.png").exists()


def test_full_screen_action_uses_existing_capture_without_region(monkeypatch, tmp_path):
    captured = {}
    image = Image.new("RGB", (8, 6), "white")

    def fake_capture_screen(region=None):
        captured["region"] = region
        return image

    monkeypatch.setattr(screenshot, "capture_screen", fake_capture_screen)
    monkeypatch.chdir(tmp_path)

    result = ActionExecutor().execute({"action": "take_screenshot", "mode": "full_screen"})

    assert result["success"] is True
    assert captured == {"region": None}
    assert list((tmp_path / "screenshots").glob("screenshot_*.png"))