"""Desktop Input & Automation Backend for MARUTI Desktop Assistant.

Provides session-aware desktop input with strict safety boundaries:
- Bounded scrolling (clamps amounts [50, 2000] and repetitions [1, 10]).
- Coordinate validation against physical display geometry.
- Wayland / X11 / Windows session detection.
- Unicode and multilingual text typing via clipboard fallback.
"""
from __future__ import annotations

import logging
import os
import platform
import time
from typing import List, Optional, Tuple

logger = logging.getLogger("maruti.input")


class DesktopInputBackend:
    """Session-aware, bounded desktop input controller."""

    # Safety limits
    MIN_SCROLL: int = 50
    MAX_SCROLL: int = 2000
    DEFAULT_SCROLL: int = 400
    LITTLE_SCROLL: int = 200
    LOT_SCROLL: int = 800
    MAX_REPETITIONS: int = 10

    def __init__(self) -> None:
        self.system = platform.system()
        self.is_wayland = bool(os.getenv("WAYLAND_DISPLAY"))
        self._pg = None
        self._screen_width, self._screen_height = self._detect_screen_size()
        logger.info(
            "DesktopInputBackend initialized (OS=%s, Wayland=%s, Resolution=%dx%d)",
            self.system,
            self.is_wayland,
            self._screen_width,
            self._screen_height,
        )

    @property
    def pg(self):
        """Lazy-loaded PyAutoGUI instance with failsafe enabled."""
        if self._pg is None:
            import pyautogui
            pyautogui.PAUSE = 0.05
            pyautogui.FAILSAFE = True  # Slam cursor to corner to abort
            self._pg = pyautogui
        return self._pg

    def _detect_screen_size(self) -> Tuple[int, int]:
        """Detect display geometry safely."""
        try:
            import pyautogui
            size = pyautogui.size()
            return int(size.width), int(size.height)
        except Exception:
            return 1920, 1080

    def get_screen_size(self) -> Tuple[int, int]:
        """Return cached screen geometry (width, height)."""
        return self._screen_width, self._screen_height

    def scroll(
        self,
        direction: str = "down",
        amount: Optional[int] = None,
        qualifier: Optional[str] = None,
        repetitions: int = 1,
    ) -> Tuple[bool, str]:
        """Execute bounded scrolling.

        Args:
            direction: 'up' or 'down'.
            amount: Pixel/tick scroll amount.
            qualifier: 'little', 'lot', 'half', etc.
            repetitions: Number of scroll cycles (bounded to max 10).

        Returns:
            Tuple of (success: bool, spoken_message: str).
        """
        dir_clean = direction.lower().strip()
        if dir_clean not in ("up", "down"):
            return False, f"Unknown scroll direction '{direction}'."

        # Determine base scroll step
        if qualifier == "little":
            step = self.LITTLE_SCROLL
        elif qualifier == "lot":
            step = self.LOT_SCROLL
        elif amount is not None:
            step = max(self.MIN_SCROLL, min(self.MAX_SCROLL, int(amount)))
        else:
            step = self.DEFAULT_SCROLL

        # Clamp repetitions to prevent unbounded runaways
        reps = max(1, min(self.MAX_REPETITIONS, int(repetitions)))

        # PyAutoGUI: positive for up, negative for down
        scroll_val = step if dir_clean == "up" else -step

        try:
            for i in range(reps):
                self.pg.scroll(scroll_val)
                if reps > 1 and i < reps - 1:
                    time.sleep(0.08)

            qual_str = f" a {qualifier}" if qualifier else ""
            rep_str = f" {reps} times" if reps > 1 else ""
            return True, f"Scrolled {dir_clean}{qual_str}{rep_str}."
        except Exception as exc:
            logger.error("Scroll execution failed: %s", exc)
            return False, f"Failed to scroll {dir_clean}: {exc}"

    def click_coordinate(self, x: int, y: int) -> Tuple[bool, str]:
        """Validate target against physical display bounds and click.

        Args:
            x: X-coordinate in screen pixels.
            y: Y-coordinate in screen pixels.

        Returns:
            Tuple of (success: bool, spoken_message: str).
        """
        w, h = self.get_screen_size()
        if x < 0 or x >= w or y < 0 or y >= h:
            msg = f"Target coordinates ({x}, {y}) are outside the screen resolution {w}x{h}."
            logger.warning(msg)
            return False, msg

        try:
            self.pg.click(x, y)
            return True, f"Clicked at ({x}, {y})."
        except Exception as exc:
            logger.error("Failed to click at (%d, %d): %s", x, y, exc)
            return False, f"Click failed: {exc}"

    def type_text(self, text: str, newline: bool = False) -> Tuple[bool, str]:
        """Type text with unicode/multilingual clipboard fallback.

        Args:
            text: Utterance or string to type.
            newline: If True, inserts newline after typing.

        Returns:
            Tuple of (success: bool, spoken_message: str).
        """
        if not text:
            return False, "No text provided to type."

        try:
            if text.isascii():
                self.pg.write(text, interval=0.02)
            else:
                from core.clipboard import set_clipboard_text
                set_clipboard_text(text)
                self.pg.hotkey("ctrl", "v")
            if newline:
                self.pg.press("enter")
            return True, f"Typed '{text}'."
        except Exception as exc:
            logger.error("Failed to type text: %s", exc)
            return False, f"Failed to type: {exc}"

    def press_key(self, key: str, repetitions: int = 1) -> Tuple[bool, str]:
        """Press an individual key one or more times.

        Args:
            key: Name of key (e.g. 'enter', 'tab', 'backspace', 'delete').
            repetitions: Number of times to press key (bounded 1 to 50).

        Returns:
            Tuple of (success: bool, spoken_message: str).
        """
        key_clean = key.lower().strip()
        reps = max(1, min(50, int(repetitions)))
        try:
            for i in range(reps):
                self.pg.press(key_clean)
                if reps > 1 and i < reps - 1:
                    time.sleep(0.04)
            rep_str = f" {reps} times" if reps > 1 else ""
            return True, f"Pressed {key_clean}{rep_str}."
        except Exception as exc:
            logger.error("Failed to press key '%s': %s", key, exc)
            return False, f"Failed to press {key}: {exc}"

    def press_keys(self, keys: List[str]) -> Tuple[bool, str]:
        """Press a keyboard shortcut combo safely.

        Args:
            keys: List of key names (e.g. ['ctrl', 'c']).

        Returns:
            Tuple of (success: bool, spoken_message: str).
        """
        if not keys:
            return False, "No keys specified."

        try:
            if len(keys) > 1:
                self.pg.hotkey(*keys)
            else:
                self.pg.press(keys[0])
            combo_label = " plus ".join(keys)
            return True, f"Pressed {combo_label}."
        except Exception as exc:
            logger.error("Failed to press keys %s: %s", keys, exc)
            return False, f"Failed to press keys: {exc}"

    def get_redo_shortcut(self) -> List[str]:
        """Return standard redo accelerator for the current desktop environment.

        On Linux GNOME Text Editor / GTK applications, standard redo is Ctrl+Shift+Z.
        On Windows / macOS, standard redo is Ctrl+Y (or Cmd+Shift+Z).
        """
        return ["ctrl", "shift", "z"] if self.system == "Linux" else ["ctrl", "y"]

    def select_all(self) -> Tuple[bool, str]:
        """Select all content in the active editor (Ctrl+A)."""
        res = self.press_keys(["ctrl", "a"])
        return res[0], "Selected all." if res[0] else res[1]

    def select_line(self, line_number: Optional[int] = None) -> Tuple[bool, str]:
        """Select a specific line or current line in the active text editor.

        For line 1: moves to document start (Ctrl+Home) and selects line text (Shift+End).
        For line N: moves to doc start, moves down (N - 1) times, moves to start of line (Home),
        and selects line text without the trailing newline (Shift+End).
        If line_number is None: moves to start of current line and selects to end (Home, Shift+End).

        Args:
            line_number: 1-indexed target line number, or None for current line.

        Returns:
            Tuple of (success: bool, spoken_message: str).
        """
        try:
            if line_number is not None:
                if line_number < 1:
                    return False, f"Invalid line number {line_number}."
                # Go to document start
                self.pg.hotkey("ctrl", "home")
                time.sleep(0.04)
                # Move down to target line
                for _ in range(line_number - 1):
                    self.pg.press("down")
                    time.sleep(0.02)
                # Align to line start
                self.pg.press("home")
                time.sleep(0.02)
                # Select line without trailing newline
                self.pg.hotkey("shift", "end")
                return True, f"Selected line {line_number}."
            else:
                self.pg.press("home")
                time.sleep(0.02)
                self.pg.hotkey("shift", "end")
                return True, "Selected current line."
        except Exception as exc:
            logger.error("Failed to select line: %s", exc)
            return False, f"Failed to select line: {exc}"

    def select_word(self, direction: str = "current") -> Tuple[bool, str]:
        """Select current, next, or previous word."""
        dir_clean = direction.lower().strip()
        try:
            if dir_clean == "next":
                self.pg.hotkey("ctrl", "right")
                time.sleep(0.02)
                self.pg.hotkey("ctrl", "shift", "right")
                return True, "Selected next word."
            elif dir_clean == "previous":
                self.pg.hotkey("ctrl", "left")
                time.sleep(0.02)
                self.pg.hotkey("ctrl", "shift", "left")
                return True, "Selected previous word."
            else:
                # Select current word: navigate word start, then select word
                self.pg.hotkey("ctrl", "left")
                time.sleep(0.02)
                self.pg.hotkey("ctrl", "shift", "right")
                return True, "Selected current word."
        except Exception as exc:
            logger.error("Failed to select word: %s", exc)
            return False, f"Failed to select word: {exc}"

    def select_to_boundary(self, boundary: str) -> Tuple[bool, str]:
        """Select text from cursor to line or document boundary."""
        b_clean = boundary.lower().strip()
        try:
            if b_clean in ("line_start", "beginning of line", "start of line"):
                self.pg.hotkey("shift", "home")
                return True, "Selected to beginning of line."
            elif b_clean in ("line_end", "end of line"):
                self.pg.hotkey("shift", "end")
                return True, "Selected to end of line."
            elif b_clean in ("doc_start", "beginning of document", "start of document"):
                self.pg.hotkey("ctrl", "shift", "home")
                return True, "Selected to beginning of document."
            elif b_clean in ("doc_end", "end of document"):
                self.pg.hotkey("ctrl", "shift", "end")
                return True, "Selected to end of document."
            else:
                return False, f"Unknown selection boundary '{boundary}'."
        except Exception as exc:
            logger.error("Failed to select to boundary %s: %s", boundary, exc)
            return False, f"Failed to select boundary: {exc}"

    def clear_selection(self) -> Tuple[bool, str]:
        """Clear active text selection by nudging cursor without altering text."""
        try:
            self.pg.press("right")
            return True, "Selection cleared."
        except Exception as exc:
            logger.error("Failed to clear selection: %s", exc)
            return False, f"Failed to clear selection: {exc}"

    def move_cursor(self, direction: str, steps: int = 1) -> Tuple[bool, str]:
        """Move cursor in specified direction."""
        dir_clean = direction.lower().strip()
        if dir_clean not in ("left", "right", "up", "down"):
            return False, f"Unknown cursor direction '{direction}'."
        reps = max(1, min(100, int(steps)))
        try:
            for _ in range(reps):
                self.pg.press(dir_clean)
            step_str = f" {reps} steps" if reps > 1 else ""
            return True, f"Moved cursor {dir_clean}{step_str}."
        except Exception as exc:
            logger.error("Failed to move cursor: %s", exc)
            return False, f"Failed to move cursor: {exc}"

    def go_to_boundary(self, boundary: str) -> Tuple[bool, str]:
        """Move cursor to document or line boundary."""
        b_clean = boundary.lower().strip()
        try:
            if b_clean in ("doc_start", "beginning of document", "start of document", "top of document"):
                self.pg.hotkey("ctrl", "home")
                return True, "Moved to the beginning of the document."
            elif b_clean in ("doc_end", "end of document", "bottom of document"):
                self.pg.hotkey("ctrl", "end")
                return True, "Moved to the end of the document."
            elif b_clean in ("line_start", "beginning of line", "start of line"):
                self.pg.press("home")
                return True, "Moved to the beginning of the line."
            elif b_clean in ("line_end", "end of line"):
                self.pg.press("end")
                return True, "Moved to the end of the line."
            else:
                return False, f"Unknown navigation boundary '{boundary}'."
        except Exception as exc:
            logger.error("Failed to go to boundary %s: %s", boundary, exc)
            return False, f"Failed to go to boundary: {exc}"

    def clipboard_copy(self) -> Tuple[bool, str]:
        """Copy active selection to system clipboard (Ctrl+C)."""
        res = self.press_keys(["ctrl", "c"])
        time.sleep(0.05)
        return True, "Copied." if res[0] else res[1]

    def clipboard_cut(self) -> Tuple[bool, str]:
        """Cut active selection to system clipboard (Ctrl+X)."""
        res = self.press_keys(["ctrl", "x"])
        time.sleep(0.05)
        return True, "Cut." if res[0] else res[1]

    def clipboard_paste(self) -> Tuple[bool, str]:
        """Paste from system clipboard (Ctrl+V)."""
        res = self.press_keys(["ctrl", "v"])
        time.sleep(0.05)
        return True, "Pasted." if res[0] else res[1]

    def edit_undo(self) -> Tuple[bool, str]:
        """Undo last editing action (Ctrl+Z)."""
        res = self.press_keys(["ctrl", "z"])
        time.sleep(0.05)
        return True, "Undone." if res[0] else res[1]

    def edit_redo(self) -> Tuple[bool, str]:
        """Redo last undone editing action (Ctrl+Shift+Z on GNOME/Linux, Ctrl+Y on Windows)."""
        shortcut = self.get_redo_shortcut()
        res = self.press_keys(shortcut)
        time.sleep(0.05)
        return True, "Redone." if res[0] else res[1]

    def delete_selected(self) -> Tuple[bool, str]:
        """Delete active selection."""
        return self.press_key("backspace")

    def find_text(self, query: Optional[str] = None) -> Tuple[bool, str]:
        """Open Find dialog (Ctrl+F) and optionally enter query."""
        self.press_keys(["ctrl", "f"])
        if query:
            time.sleep(0.1)
            self.type_text(query, newline=True)
            return True, f"Finding '{query}'."
        return True, "Opened find dialog."

    def replace_text(self, find_query: Optional[str] = None, replace_query: Optional[str] = None) -> Tuple[bool, str]:
        """Open Replace dialog (Ctrl+H)."""
        self.press_keys(["ctrl", "h"])
        return True, "Opened replace dialog."

    def save_file(self) -> Tuple[bool, str]:
        """Save active document (Ctrl+S)."""
        return self.press_keys(["ctrl", "s"])

    def save_file_as(self) -> Tuple[bool, str]:
        """Save active document as new file (Ctrl+Shift+S)."""
        return self.press_keys(["ctrl", "shift", "s"])
