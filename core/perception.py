"""Screen Perception & OCR Module for MARUTI Desktop Assistant.

Handles desktop screen capture, OCR extraction, UI element targeting,
video card identification, and visible text summarization.
Enforces local privacy: zero transmission of screen data to external cloud services.
Handles Wayland / X11 / Windows / headless / missing Tesseract environments gracefully.
Supports multi-backend screenshot capture, DPI display scaling compensation,
and safe multi-tier element matching with ambiguity detection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import logging
import math
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
    x: int  # Center X coordinate in virtual screen pixels
    y: int  # Center Y coordinate in virtual screen pixels
    width: int
    height: int
    confidence: float
    kind: str = "text"  # 'text', 'button', 'video', 'link'
    left: int = 0
    top: int = 0


@dataclass
class TargetMatchResult:
    """Detailed outcome of a target search across screen elements."""

    status: str  # 'found', 'ambiguous', 'not_found', 'no_text', 'capture_failed', 'no_ocr'
    element: Optional[ScreenElement] = None
    candidates: List[ScreenElement] = field(default_factory=list)
    message: str = ""
    match_tier: str = ""  # 'exact', 'word_boundary', 'prefix', 'substring', 'fuzzy'
    match_score: float = 0.0


class PerceptionEngine:
    """Analyzes desktop display and extracts interactive visual elements."""

    def __init__(self, tesseract_cmd: Optional[str] = None) -> None:
        self.tesseract_cmd = tesseract_cmd or config.TESSERACT_CMD
        self._last_screenshot = None
        self._last_capture_time: float = 0.0
        self._cache_validity_sec: float = 1.5
        self._tesseract_available: Optional[bool] = None
        self.scale_x: float = 1.0
        self.scale_y: float = 1.0
        self.last_capture_error: Optional[str] = None

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
        """Capture screenshot safely using multi-backend fallback.

        Tries:
        1. PyAutoGUI screenshot
        2. PIL.ImageGrab (native Windows/macOS/X11)
        3. PySide6 active QScreen grab (if Qt GUI application is running)
        4. Linux CLI capture tools (gnome-screenshot, scrot, grim)

        Calculates DPI scaling factors to compensate for Retina/High-DPI displays.
        """
        now = time.time()
        if not force_fresh and self._last_screenshot and (now - self._last_capture_time < self._cache_validity_sec):
            return self._last_screenshot

        img = None
        errors: List[str] = []

        # Backend 1: PyAutoGUI screenshot
        try:
            import pyautogui

            img = pyautogui.screenshot()
        except Exception as exc:
            errors.append(f"pyautogui: {exc}")

        # Backend 2: PIL.ImageGrab
        if img is None:
            try:
                from PIL import ImageGrab

                img = ImageGrab.grab()
            except Exception as exc:
                errors.append(f"ImageGrab: {exc}")

        # Backend 3: PySide6 QScreen grab if Qt application is active
        if img is None:
            try:
                from PySide6.QtGui import QGuiApplication

                app = QGuiApplication.instance()
                if app:
                    screen = QGuiApplication.primaryScreen()
                    if screen:
                        pixmap = screen.grabWindow(0)
                        if not pixmap.isNull():
                            from PIL import Image
                            import io

                            buf = io.BytesIO()
                            pixmap.save(buf, "PNG")
                            buf.seek(0)
                            img = Image.open(buf)
            except Exception as exc:
                errors.append(f"QtQScreen: {exc}")

        # Backend 4: Linux CLI capture tools
        if img is None and shutil.which("gnome-screenshot"):
            try:
                import subprocess
                import tempfile
                from PIL import Image

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                    tmp_path = tf.name
                subprocess.run(["gnome-screenshot", "-f", tmp_path], check=True, timeout=3)
                img = Image.open(tmp_path).copy()
                os.unlink(tmp_path)
            except Exception as exc:
                errors.append(f"gnome-screenshot: {exc}")

        if img is None:
            self.last_capture_error = "; ".join(errors) if errors else "No screenshot backend succeeded"
            logger.debug("Failed to capture screenshot: %s", self.last_capture_error)
            return None

        self.last_capture_error = None
        self._last_screenshot = img
        self._last_capture_time = now

        # Compute display scaling factor (High-DPI / 125% / 150% scaling)
        try:
            import pyautogui

            screen_w, screen_h = pyautogui.size()
        except Exception:
            screen_w, screen_h = img.width, img.height

        self.scale_x = screen_w / img.width if img.width else 1.0
        self.scale_y = screen_h / img.height if img.height else 1.0

        return img

    def extract_elements(self, min_conf: float = 25.0) -> List[ScreenElement]:
        """Run OCR on current screen and extract positioned interactive elements.

        Compensates for display scaling and normalizes text bounding boxes.
        """
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

            # Multi-pass OCR: try sparse text mode (PSM 11) first for UI elements
            data = None
            try:
                data = pytesseract.image_to_data(img, config="--psm 11", output_type=pytesseract.Output.DICT)
            except Exception:
                data = None

            # Fall back to default page segmentation if PSM 11 returned nothing
            has_words = data and any(bool(t.strip()) for t in data.get("text", []))
            if not has_words:
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

            elements: List[ScreenElement] = []
            num_boxes = len(data.get("text", []))

            for i in range(num_boxes):
                text_val = data["text"][i]
                clean = text_val.strip()
                if not clean:
                    continue

                try:
                    conf = float(data["conf"][i])
                except (ValueError, TypeError):
                    conf = 0.0

                # Accept clean words matching minimum confidence
                if conf < min_conf and len(clean) > 2:
                    continue

                raw_left = data["left"][i]
                raw_top = data["top"][i]
                raw_w = data["width"][i]
                raw_h = data["height"][i]

                if raw_w <= 0 or raw_h <= 0:
                    continue

                # Map raw screenshot pixels to virtual desktop screen coordinates
                left = int(raw_left * self.scale_x)
                top = int(raw_top * self.scale_y)
                w = max(1, int(raw_w * self.scale_x))
                h = max(1, int(raw_h * self.scale_y))
                center_x = left + w // 2
                center_y = top + h // 2

                elements.append(
                    ScreenElement(
                        text=clean,
                        x=center_x,
                        y=center_y,
                        width=w,
                        height=h,
                        confidence=round(max(0.1, conf / 100.0), 2),
                        left=left,
                        top=top,
                    )
                )

            return elements
        except Exception as exc:
            logger.error("OCR execution failed: %s", exc)
            return []

    def _build_phrase_candidates(self, elements: List[ScreenElement]) -> List[ScreenElement]:
        """Group adjacent OCR tokens on the same horizontal line into multi-word phrases.

        Ensures that phrases like 'Sign In', 'Open File', 'Google Chrome' are treated as
        coherent clickable units without arbitrary coordinate jumping.
        """
        candidates = list(elements)
        n_elements = len(elements)

        # Build 2-word, 3-word, and 4-word phrase combinations on the same text baseline
        for window_size in (2, 3, 4):
            for i in range(n_elements - window_size + 1):
                window = elements[i : i + window_size]
                is_same_line = True

                for k in range(len(window) - 1):
                    w1, w2 = window[k], window[k + 1]
                    # Vertical alignment check: baselines must align within line height tolerance
                    if abs(w1.y - w2.y) > max(w1.height, w2.height) * 0.7:
                        is_same_line = False
                        break
                    # Horizontal gap check: words must be in natural horizontal reading sequence
                    gap = w2.left - (w1.left + w1.width)
                    if gap < -5 or gap > max(w1.height, 20) * 2.2:
                        is_same_line = False
                        break

                if is_same_line:
                    comb_text = " ".join(w.text for w in window)
                    comb_left = window[0].left
                    comb_top = min(w.top for w in window)
                    comb_w = (window[-1].left + window[-1].width) - comb_left
                    comb_h = max(w.top + w.height for w in window) - comb_top
                    avg_conf = sum(w.confidence for w in window) / window_size

                    candidates.append(
                        ScreenElement(
                            text=comb_text,
                            x=comb_left + comb_w // 2,
                            y=comb_top + comb_h // 2,
                            width=comb_w,
                            height=comb_h,
                            confidence=round(avg_conf, 2),
                            left=comb_left,
                            top=comb_top,
                        )
                    )

        return candidates

    def find_target_detailed(self, target_label: str) -> TargetMatchResult:
        """Locate target element using hierarchical text matching and ambiguity detection.

        Tiers:
        1. Exact match (case-insensitive, normalized punctuation)
        2. Word boundary match (target is an exact word inside element text)
        3. Prefix match (element starts with target)
        4. Substring match (target is contained in element)
        5. Fuzzy match (SequenceMatcher score >= 0.82)

        Returns:
            TargetMatchResult with status 'found', 'ambiguous', 'not_found', 'no_text',
            'capture_failed', or 'no_ocr'.
        """
        if not self.is_ocr_available():
            return TargetMatchResult(
                status="no_ocr",
                message="Tesseract OCR is not installed. Screen reading requires tesseract-ocr.",
            )

        clean_target = re.sub(r"[^\w\s]", "", target_label.lower()).strip()
        clean_target = re.sub(r"\s+", " ", clean_target)
        if not clean_target:
            return TargetMatchResult(
                status="not_found",
                message="No valid target text specified to click.",
            )

        elements = self.extract_elements(min_conf=25.0)
        if not elements:
            if self.last_capture_error:
                return TargetMatchResult(
                    status="capture_failed",
                    message=f"Could not capture screen: {self.last_capture_error}",
                )
            return TargetMatchResult(
                status="no_text",
                message="No readable text was detected on the active desktop screen.",
            )

        candidates = self._build_phrase_candidates(elements)

        # Multi-tier match collection
        tier_matches: Dict[int, List[Tuple[float, ScreenElement, str]]] = {
            1: [],
            2: [],
            3: [],
            4: [],
            5: [],
        }

        for cand in candidates:
            cand_clean = re.sub(r"[^\w\s]", "", cand.text.lower()).strip()
            cand_clean = re.sub(r"\s+", " ", cand_clean)
            if not cand_clean:
                continue

            # Tier 1: Exact match
            if cand_clean == clean_target:
                tier_matches[1].append((1.0, cand, "exact"))
            # Tier 2: Word boundary match
            elif re.search(rf"\b{re.escape(clean_target)}\b", cand_clean):
                tier_matches[2].append((0.95, cand, "word_boundary"))
            # Tier 3: Prefix match
            elif cand_clean.startswith(clean_target) and len(clean_target) >= 3:
                tier_matches[3].append((0.90, cand, "prefix"))
            # Tier 4: Substring match
            elif clean_target in cand_clean and len(clean_target) >= 3:
                tier_matches[4].append((0.85, cand, "substring"))
            # Tier 5: Fuzzy match
            else:
                ratio = SequenceMatcher(None, clean_target, cand_clean).ratio()
                if ratio >= 0.82:
                    tier_matches[5].append((ratio, cand, "fuzzy"))

        # Select highest priority tier with matches
        for tier in (1, 2, 3, 4, 5):
            matches = tier_matches[tier]
            if not matches:
                continue

            # Filter duplicate detections of the same physical spot (within 15px)
            unique_matches: List[Tuple[float, ScreenElement, str]] = []
            for score, el, tier_name in matches:
                if not any(math.hypot(el.x - u[1].x, el.y - u[1].y) < 15 for u in unique_matches):
                    unique_matches.append((score, el, tier_name))

            if len(unique_matches) == 1:
                score, el, tier_name = unique_matches[0]
                return TargetMatchResult(
                    status="found",
                    element=el,
                    match_tier=tier_name,
                    match_score=score,
                    message=f"Located '{el.text}' on screen.",
                )

            # Check if all matches represent the same physical element (within 30px)
            all_close = all(
                math.hypot(unique_matches[0][1].x - u[1].x, unique_matches[0][1].y - u[1].y) <= 30
                for u in unique_matches
            )
            if all_close:
                score, el, tier_name = unique_matches[0]
                return TargetMatchResult(
                    status="found",
                    element=el,
                    match_tier=tier_name,
                    match_score=score,
                    message=f"Located '{el.text}' on screen.",
                )

            # Multiple distinct elements on screen at different positions: safely report ambiguity
            distinct_elements = [u[1] for u in unique_matches]
            return TargetMatchResult(
                status="ambiguous",
                candidates=distinct_elements,
                message=(
                    f"Multiple elements matching '{target_label}' were found at different locations on screen "
                    f"({len(distinct_elements)} matches). Please specify which one (e.g. top {target_label} menu)."
                ),
            )

        return TargetMatchResult(
            status="not_found",
            message=f"Could not find any visible element matching '{target_label}' on the screen.",
        )

    def find_target(self, target_label: str) -> Optional[ScreenElement]:
        """Locate target element across screen elements (backward compatible).

        Returns:
            ScreenElement if an unambiguous match is found, otherwise None.
        """
        res = self.find_target_detailed(target_label)
        return res.element if res.status == "found" else None

    def describe_screen(self) -> str:
        """Generate a concise spoken summary of what is currently on screen."""
        if not self.is_ocr_available():
            return (
                "I can see your active desktop window, but Tesseract OCR is not installed "
                "to read the exact text. You can install it with sudo apt install tesseract-ocr."
            )

        elements = self.extract_elements(min_conf=35.0)
        if not elements:
            return "The screen appears to have minimal or unreadable text right now."

        words = [e.text for e in elements]
        meaningful = [w for w in words if len(w) > 2 and not w.isdigit()]
        sample = ", ".join(meaningful[:10])
        total_words = len(words)
        return f"I can see approximately {total_words} words on your screen, including: {sample}."

    def read_visible_text(self, max_words: int = 40) -> str:
        """Extract and return visible screen text as readable lines."""
        if not self.is_ocr_available():
            return "Tesseract OCR is not installed. Please install tesseract-ocr to read visible screen text."

        elements = self.extract_elements(min_conf=35.0)
        if not elements:
            return "No clear text could be detected on the screen."

        extracted_text = " ".join(e.text for e in elements[:max_words])
        return f"Visible text: {extracted_text}"

    def find_video_elements(self) -> List[ScreenElement]:
        """Detect visible video cards on video sites sorted by vertical position."""
        elements = self.extract_elements(min_conf=30.0)
        timestamp_re = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
        videos: List[ScreenElement] = []

        for el in elements:
            if timestamp_re.match(el.text):
                videos.append(
                    ScreenElement(
                        text="Video Card",
                        x=el.x - 50,
                        y=max(0, el.y - 40),
                        width=el.width + 120,
                        height=el.height + 80,
                        confidence=0.85,
                        kind="video",
                    )
                )

        if not videos:
            candidates = [el for el in elements if el.y > 180 and len(el.text) > 4]
            candidates.sort(key=lambda e: e.y)
            for c in candidates[:6]:
                videos.append(
                    ScreenElement(
                        text=c.text,
                        x=c.x,
                        y=c.y,
                        width=c.width,
                        height=c.height,
                        confidence=0.75,
                        kind="video",
                    )
                )

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
