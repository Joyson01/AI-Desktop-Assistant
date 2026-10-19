from pathlib import Path

from PIL import ImageGrab


def capture_screen(region=None, debug_path=None):
    """Capture the desktop, optionally restricting the capture to a region."""
    image = ImageGrab.grab(bbox=region, all_screens=True)
    if debug_path:
        path = Path(debug_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
    return image