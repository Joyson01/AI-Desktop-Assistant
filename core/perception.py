"""Screen Perception & OCR Module for MARUTI Desktop Assistant.

Handles desktop screen capture, OCR extraction, UI element targeting,
video card identification, and visible text summarization.
Enforces local privacy: zero transmission of screen data to external cloud services.
Handles Wayland / headless / missing Tesseract environments gracefully.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import logging
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

import config

logger = logging.getLogger("maruti.perception")


@dataclass
class ScreenElement:
    """Represents a located visual UI element on screen."""
    text: str
    x: int  # Center X coordinate
    y: int  # Center Y coordinate
    width: int
    height: int
    confidence: float
    kind: str = "text"  # 'text', 'button', 'video', 'link'


class PerceptionEngine:
    """Analyzes desktop display and extracts interactive visual elements."""

    def __init__(self, tesseract_cmd: Optional[str] = None) -> None:
        self.tesseract_cmd = tesseract_cmd or config.TESSERACT_CMD
        self._last_screenshot = None
        self._last_capture_time: float = 0.0
        self._cache_validity_sec: float = 2.0  # Invalidate after 2 seconds or after actions
        self._tesseract_available: Optional[bool] = None

    def is_ocr_available(self) -> bool:
        """Verify if Tesseract OCR binary is reachable."""
        if self._tesseract_available is not None:
            return self._tesseract_available

        if self.tesseract_cmd and os.path.isfile(self.tesseract_cmd):
            self._tesseract_available = True
            return True

        if shutil.which("tesseract"):
            self._tesseract_available = True
            return True

        self._tesseract_available = False
        return False

    def invalidate_cache(self) -> None:
        """Clear cached screenshot after desktop navigation or scroll."""
        self._last_screenshot = None
        self._last_capture_time = 0.0

    def capture_screen(self, force_fresh: bool = False):
        """Capture screenshot safely using PyAutoGUI/Pillow."""
        now = time.time()
        if not force_fresh and self._last_screenshot and (now - self._last_capture_time < self._cache_validity_sec):
            return self._last_screenshot

        try:
            import pyautogui
            img = pyautogui.screenshot()
            self._last_screenshot = img
            self._last_capture_time = now
            return img
        except Exception as exc:
            logger.error("Failed to capture screenshot: %s", exc)
            return None

    def extract_elements(self, min_conf: float = 35.0) -> List[ScreenElement]:
        """Run OCR on the current screen and extract located text elements."""
        if not self.is_ocr_available():
            logger.info("Tesseract binary not installed; OCR extraction unavailable.")
            return []

        img = self.capture_screen()
        if img is None:
            return []

        try:
            import pytesseract
            if self.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            elements: List[ScreenElement] = []

            for i, text in enumerate(data.get("text", [])):
                clean = text.strip()
                try:
                    conf = float(data["conf"][i])
                except (ValueError, TypeError):
                    conf = 0.0

                if clean and conf >= min_conf:
                    x = int(data["left"][i] + data["width"][i] / 2)
                    y = int(data["top"][i] + data["height"][i] / 2)
                    elements.append(ScreenElement(
                        text=clean,
                        x=x,
                        y=y,
                        width=data["width"][i],
                        height=data["height"][i],
                        confidence=round(conf / 100.0, 2),
                    ))

            return elements
        except Exception as exc:
            logger.error("OCR execution failed: %s", exc)
            return []

    def describe_screen(self) -> str:
        """Generate a concise spoken summary of what is currently on screen."""
        if not self.is_ocr_available():
            return (
                "I can see your active desktop window, but Tesseract OCR is not installed "
                "to read the exact text. You can install it with sudo apt install tesseract-ocr."
            )

        elements = self.extract_elements(min_conf=45.0)
        if not elements:
            return "The screen appears to have minimal or unreadable text right now."

        # Collect distinct lines/phrases
        words = [e.text for e in elements]
        # Filter common noise
        meaningful = [w for w in words if len(w) > 2 and not w.isdigit()]
        sample = ", ".join(meaningful[:10])

        total_words = len(words)
        return f"I can see approximately {total_words} words on your screen, including: {sample}."

    def read_visible_text(self, max_words: int = 40) -> str:
        """Extract and return visible screen text as readable lines."""
        if not self.is_ocr_available():
            return "Tesseract OCR is not installed. Please install tesseract-ocr to read visible screen text."

        elements = self.extract_elements(min_conf=40.0)
        if not elements:
            return "No clear text could be detected on the screen."

        extracted_text = " ".join(e.text for e in elements[:max_words])
        return f"Visible text: {extracted_text}"

    def find_target(self, target_label: str) -> Optional[ScreenElement]:
        """Fuzzy match a target label across screen elements."""
        if not self.is_ocr_available():
            return None

        elements = self.extract_elements(min_conf=35.0)
        if not elements:
            return None

        label_clean = target_label.strip().lower()
        n_words = max(1, len(label_clean.split()))

        # Check multi-word window combinations
        best_match: Optional[Tuple[float, ScreenElement]] = None
        for i in range(len(elements) - n_words + 1):
            window = elements[i : i + n_words]
            candidate_text = " ".join(e.text for e in window).lower()
            score = SequenceMatcher(None, label_clean, candidate_text).ratio()

            if best_match is None or score > best_match[0]:
                center_x = int(sum(e.x for e in window) / n_words)
                center_y = int(sum(e.y for e in window) / n_words)
                combined = ScreenElement(
                    text=" ".join(e.text for e in window),
                    x=center_x,
                    y=center_y,
                    width=sum(e.width for e in window),
                    height=max(e.height for e in window),
                    confidence=score,
                )
                best_match = (score, combined)

        if best_match and best_match[0] >= 0.60:
            return best_match[1]

        return None

    def find_video_elements(self) -> List[ScreenElement]:
        """Detect visible video cards on video sites sorted by vertical position."""
        elements = self.extract_elements(min_conf=35.0)
        timestamp_re = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
        videos: List[ScreenElement] = []

        for el in elements:
            if timestamp_re.match(el.text):
                videos.append(ScreenElement(
                    text="Video Card",
                    x=el.x - 50,
                    y=max(0, el.y - 40),
                    width=el.width + 120,
                    height=el.height + 80,
                    confidence=0.85,
                    kind="video",
                ))

        if not videos:
            # Fallback: identify distinct blocks below header area
            candidates = [el for el in elements if el.y > 180 and len(el.text) > 4]
            candidates.sort(key=lambda e: e.y)
            for c in candidates[:6]:
                videos.append(ScreenElement(
                    text=c.text,
                    x=c.x,
                    y=c.y,
                    width=c.width,
                    height=c.height,
                    confidence=0.75,
                    kind="video",
                ))

        videos.sort(key=lambda v: v.y)
        return videos

    def find_video_by_index(self, index: int = 1) -> Optional[ScreenElement]:
        """Return video card for 1-based index (1 for first, 2 for second, etc.)."""
        videos = self.find_video_elements()
        if not videos:
            return None
        target_idx = max(0, min(len(videos) - 1, index - 1))
        return videos[target_idx]

    def find_first_video(self) -> Optional[ScreenElement]:
        """Detect the first visible video result or thumbnail on YouTube/video sites."""
        return self.find_video_by_index(1)
