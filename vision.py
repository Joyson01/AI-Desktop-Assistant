"""Screenshot + OCR with coordinates -> click targets (slides 8-10)."""
from dataclasses import dataclass
from difflib import SequenceMatcher

from config import TESSERACT_CMD


@dataclass
class Match:
    x: int
    y: int
    text: str
    score: float  # fuzzy similarity 0..1 (this is the "confidence" the soft-computing layer uses)


def find_text(label: str, min_ocr_conf: float = 40.0):
    import pyautogui
    import pytesseract
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    img = pyautogui.screenshot()
    d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    words = []
    for i, txt in enumerate(d["text"]):
        if txt.strip() and float(d["conf"][i]) >= min_ocr_conf:
            words.append((txt, d["left"][i], d["top"][i], d["width"][i], d["height"][i]))
    n = max(1, len(label.split()))
    best = None
    for i in range(len(words) - n + 1):
        chunk = words[i:i + n]
        text = " ".join(w[0] for w in chunk)
        score = SequenceMatcher(None, label.lower(), text.lower()).ratio()
        if best is None or score > best[0]:
            best = (score, chunk, text)
    if best is None:
        return None
    score, chunk, text = best
    x = int(sum(w[1] + w[3] / 2 for w in chunk) / n)
    y = int(sum(w[2] + w[4] / 2 for w in chunk) / n)
    return Match(x, y, text, round(score, 2))
