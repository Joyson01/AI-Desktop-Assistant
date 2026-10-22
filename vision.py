"""Screenshot + OCR with coordinates -> click targets (slides 8-10)."""
from dataclasses import dataclass
from typing import Optional

from config import TESSERACT_CMD
from core.perception import PerceptionEngine


@dataclass
class Match:
    x: int
    y: int
    text: str
    score: float  # fuzzy similarity 0..1 (this is the "confidence" the soft-computing layer uses)


def find_text(label: str, min_ocr_conf: float = 25.0) -> Optional[Match]:
    """Locate target text on screen using robust PerceptionEngine with DPI scaling."""
    engine = PerceptionEngine(tesseract_cmd=TESSERACT_CMD)
    match_res = engine.find_target_detailed(label)
    if match_res.status == "found" and match_res.element:
        el = match_res.element
        return Match(x=el.x, y=el.y, text=el.text, score=round(match_res.match_score, 2))
    return None
