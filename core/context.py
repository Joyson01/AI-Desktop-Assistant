"""Conversation and Desktop Context State for MARUTI Desktop Assistant.

Maintains persistent, structured state for:
- Active desktop application and window.
- Active browser, website domain, and URL.
- Page navigation state (e.g. 'homepage', 'search_results', 'watch').
- Last query searched.
- Last executed action and outcome.
- Observed screen elements cache with validity timestamps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("maruti.context")


@dataclass
class ConversationContext:
    """Tracks active application, web context, and follow-up command state."""

    target_app: Optional[str] = None
    active_browser: Optional[str] = None
    current_site: Optional[str] = None
    current_url: Optional[str] = None
    page_state: str = "initial"  # 'initial', 'homepage', 'search_results', 'watch', 'playing', 'paused'
    last_query: Optional[str] = None
    last_action: Optional[str] = None
    last_result: Optional[str] = None
    last_updated: float = field(default_factory=time.time)
    pending_workflow: Optional[str] = None
    observed_elements: List[Dict[str, Any]] = field(default_factory=list)
    cache_validity_sec: float = 3.0
    last_speech_submission: Optional[str] = None
    last_submission_time: float = 0.0

    # Editor and Document State
    active_editor: Optional[str] = None
    editor_buffer: List[str] = field(default_factory=list)
    cursor_line: int = 0
    cursor_col: int = 0
    selected_text: Optional[str] = None
    clipboard_content: Optional[str] = None
    undo_stack: List[List[str]] = field(default_factory=list)
    redo_stack: List[List[str]] = field(default_factory=list)
    is_dictation_mode: bool = False

    def sync_desktop_state(self) -> None:
        """Attempt to inspect active desktop window to keep app and browser state synchronized."""
        import shutil
        import subprocess

        try:
            if shutil.which("xdotool"):
                res = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    capture_output=True,
                    text=True,
                    timeout=0.5,
                )
                if res.returncode == 0 and res.stdout.strip():
                    title = res.stdout.strip().lower()
                    if "youtube" in title:
                        self.current_site = "youtube"
                    for b in ("chrome", "chromium", "firefox", "edge"):
                        if b in title:
                            self.active_browser = "chrome" if "chrome" in b else b
                            break
        except Exception as exc:
            logger.debug("Desktop state synchronization skipped: %s", exc)

    def update_app(self, app_name: str) -> None:
        """Record newly opened or focused desktop application."""
        clean = app_name.lower().strip()
        self.target_app = clean
        self.last_updated = time.time()
        # If it's a browser, set active_browser
        if clean in ("chrome", "google-chrome", "firefox", "edge", "browser"):
            self.active_browser = clean
        else:
            # If switching to a non-browser desktop app, reset current website context
            self.current_site = None
            self.current_url = None
        logger.debug("Context updated: active_app=%s", self.target_app)

    def update_site(self, site_name: str, url: str, page_state: str = "homepage") -> None:
        """Record newly visited website or web application."""
        self.current_site = site_name.lower().strip()
        self.current_url = url
        self.page_state = page_state
        self.target_app = self.active_browser or "chrome"
        self.last_updated = time.time()
        logger.debug("Context updated: site=%s, state=%s, url=%s", self.current_site, self.page_state, self.current_url)

    def update_search(self, query: str, site: str = "youtube") -> None:
        """Record active search query on website."""
        self.last_query = query.strip()
        self.current_site = site.lower().strip()
        self.page_state = "search_results"
        self.last_updated = time.time()
        logger.debug("Context updated: search_query='%s' on %s", self.last_query, self.current_site)

    def update_media_state(self, state: str) -> None:
        """Record media playback state ('playing', 'paused')."""
        self.page_state = state
        self.last_updated = time.time()
        logger.debug("Context updated: media_state=%s", state)

    def update_action(self, action_name: str, result_message: str) -> None:
        """Record last executed action and result."""
        self.last_action = action_name
        self.last_result = result_message
        self.last_updated = time.time()

    def is_youtube_active(self) -> bool:
        """Check if YouTube is the active target context."""
        return self.current_site == "youtube" or (
            bool(self.current_url and "youtube.com" in self.current_url)
        )

    def is_editor_active(self) -> bool:
        """Check if a text editor application is currently active."""
        return self.target_app in ("notepad", "gnome-text-editor", "gedit", "kate", "mousepad", "xed", "code")

    def record_text_input(self, text: str, newline: bool = False) -> None:
        """Record typed or dictated text in document model."""
        self.undo_stack.append(list(self.editor_buffer))
        self.redo_stack.clear()
        if newline or not self.editor_buffer:
            self.editor_buffer.append(text)
        else:
            self.editor_buffer[-1] += text
        self.cursor_line = len(self.editor_buffer) - 1
        self.cursor_col = len(self.editor_buffer[-1])
        self.selected_text = None
        self.last_updated = time.time()

    def record_newline(self) -> None:
        """Record a newline insertion."""
        self.undo_stack.append(list(self.editor_buffer))
        self.redo_stack.clear()
        self.editor_buffer.append("")
        self.cursor_line = len(self.editor_buffer) - 1
        self.cursor_col = 0
        self.selected_text = None
        self.last_updated = time.time()

    def record_selection(self, selection_type: str, line_number: Optional[int] = None) -> Optional[str]:
        """Record text selection state."""
        if line_number is not None:
            if 1 <= line_number <= len(self.editor_buffer):
                self.selected_text = self.editor_buffer[line_number - 1]
                self.cursor_line = line_number - 1
                self.cursor_col = len(self.selected_text)
            else:
                self.selected_text = ""
        elif selection_type == "all":
            self.selected_text = "\n".join(self.editor_buffer)
        elif selection_type == "line":
            if 0 <= self.cursor_line < len(self.editor_buffer):
                self.selected_text = self.editor_buffer[self.cursor_line]
            else:
                self.selected_text = ""
        elif selection_type == "word":
            if 0 <= self.cursor_line < len(self.editor_buffer):
                line = self.editor_buffer[self.cursor_line]
                words = line.split()
                self.selected_text = words[-1] if words else ""
        self.last_updated = time.time()
        return self.selected_text

    def record_clipboard_copy(self, text: Optional[str] = None) -> str:
        """Record copied text in context clipboard."""
        val = text if text is not None else (self.selected_text or "")
        self.clipboard_content = val
        self.last_updated = time.time()
        return val

    def record_clipboard_cut(self) -> str:
        """Record cut text and remove selected text from document model."""
        self.undo_stack.append(list(self.editor_buffer))
        self.redo_stack.clear()
        val = self.selected_text or ""
        self.clipboard_content = val
        if self.selected_text == "\n".join(self.editor_buffer):
            self.editor_buffer = [""]
            self.cursor_line = 0
            self.cursor_col = 0
        elif self.selected_text and 0 <= self.cursor_line < len(self.editor_buffer):
            self.editor_buffer[self.cursor_line] = ""
            self.cursor_col = 0
        self.selected_text = None
        self.last_updated = time.time()
        return val

    def record_clipboard_paste(self, text: Optional[str] = None) -> str:
        """Record pasted text into document model."""
        self.undo_stack.append(list(self.editor_buffer))
        self.redo_stack.clear()
        val = text if text is not None else (self.clipboard_content or "")
        if not self.editor_buffer:
            self.editor_buffer = [val]
        else:
            if self.cursor_line < len(self.editor_buffer):
                if self.selected_text:
                    self.editor_buffer[self.cursor_line] = val
                else:
                    self.editor_buffer[self.cursor_line] += val
            else:
                self.editor_buffer.append(val)
        self.cursor_line = len(self.editor_buffer) - 1
        self.cursor_col = len(self.editor_buffer[-1])
        self.selected_text = None
        self.last_updated = time.time()
        return val

    def record_undo(self) -> bool:
        """Record undo operation."""
        if not self.undo_stack:
            return False
        self.redo_stack.append(list(self.editor_buffer))
        self.editor_buffer = self.undo_stack.pop()
        self.cursor_line = max(0, len(self.editor_buffer) - 1)
        self.cursor_col = len(self.editor_buffer[-1]) if self.editor_buffer else 0
        self.selected_text = None
        self.last_updated = time.time()
        return True

    def record_redo(self) -> bool:
        """Record redo operation."""
        if not self.redo_stack:
            return False
        self.undo_stack.append(list(self.editor_buffer))
        self.editor_buffer = self.redo_stack.pop()
        self.cursor_line = max(0, len(self.editor_buffer) - 1)
        self.cursor_col = len(self.editor_buffer[-1]) if self.editor_buffer else 0
        self.selected_text = None
        self.last_updated = time.time()
        return True

    def get_document_text(self) -> str:
        """Return complete modeled document string."""
        return "\n".join(self.editor_buffer)

    def is_browser_active(self) -> bool:
        """Check if a browser is currently focused or active."""
        return bool(self.current_site or self.active_browser or (self.target_app in ("chrome", "browser", "firefox", "edge")))

    def is_duplicate_submission(self, text: str, window_sec: float = 2.5) -> bool:
        """Check if identical command text was submitted within window_sec."""
        norm = text.strip().lower()
        now = time.time()
        if norm and norm == self.last_speech_submission and (now - self.last_submission_time < window_sec):
            return True
        self.last_speech_submission = norm
        self.last_submission_time = now
        return False

    def reset(self) -> None:
        """Reset context state to initial clean state."""
        self.target_app = None
        self.active_browser = None
        self.current_site = None
        self.current_url = None
        self.page_state = "initial"
        self.last_query = None
        self.last_action = None
        self.last_result = None
        self.last_updated = time.time()
        self.pending_workflow = None
        self.observed_elements.clear()
        self.active_editor = None
        self.editor_buffer.clear()
        self.cursor_line = 0
        self.cursor_col = 0
        self.selected_text = None
        self.clipboard_content = None
        self.undo_stack.clear()
        self.redo_stack.clear()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize context for diagnostics and testing."""
        return {
            "target_app": self.target_app,
            "active_editor": self.active_editor,
            "active_browser": self.active_browser,
            "current_site": self.current_site,
            "current_url": self.current_url,
            "page_state": self.page_state,
            "last_query": self.last_query,
            "last_action": self.last_action,
            "last_result": self.last_result,
            "selected_text": self.selected_text,
            "document_text": self.get_document_text(),
            "age_seconds": round(time.time() - self.last_updated, 2),
        }
