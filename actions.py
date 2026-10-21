"""Action engine for MARUTI Desktop Assistant.

Executes an Intent and returns the sentence Maruti should speak.
Backed by the CentralActionRegistry and PolicyEngine for safety,
bounded execution, PipeWire/ALSA volume control, and browser automation.
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time
import webbrowser
from importlib.util import find_spec
from urllib.parse import quote_plus

from core.action_registry import CentralActionRegistry
from core.audio import AudioController
from core.input import DesktopInputBackend
from core.perception import PerceptionEngine
from core.policy import ActionRisk, ActionResult, PolicyEngine
from core.system_control import SystemController
import registry
from config import ACT_THRESHOLD, ASK_THRESHOLD

log = logging.getLogger("maruti.actions")
SYSTEM = platform.system()


class ActionExecutor:
    """Dispatches validated intents to desktop automation handlers."""

    def __init__(self, brain=None, dry_run: bool = False, confirm=None, context=None):
        self.brain = brain
        self.dry_run = dry_run
        self.confirm = confirm or (lambda q: False)  # Safety gate: asks user yes/no
        self.context = context
        self._pg = None
        self.registry = CentralActionRegistry(
            brain=brain,
            dry_run=dry_run,
            confirm_callback=self.confirm,
            context=context,
        )

    # ---- helpers -------------------------------------------------------
    @property
    def pg(self):
        if self._pg is None:
            import pyautogui
            pyautogui.PAUSE = 0.05
            pyautogui.FAILSAFE = True
            self._pg = pyautogui
        return self._pg

    @property
    def audio(self) -> AudioController:
        return self.registry.audio

    @property
    def input(self) -> DesktopInputBackend:
        return self.registry.input

    @property
    def perception(self) -> PerceptionEngine:
        return self.registry.perception

    @property
    def system_control(self) -> SystemController:
        return self.registry.system

    def _act(self, fn):
        if self.dry_run:
            log.info("DRY-RUN: skipped side effect")
            return
        fn()

    def _launch(self, canon):
        """Launch a desktop app by its canonical registry name with fallback chain."""
        return self.registry.system.open_application(canon)

    def _type(self, text):
        return self.registry.input.type_text(text)

    # ---- dispatcher ----------------------------------------------------
    def execute(self, intent) -> str:
        """Route intent through the central registry and return spoken response."""
        handler = getattr(self, f"do_{intent.name}", None)
        if handler is not None:
            try:
                return handler(**intent.args)
            except Exception as exc:
                log.exception("Action failed")
                return f"Sorry, that failed: {exc}"
        result = self.registry.dispatch(intent.name, intent.args)
        return result.message

    # ---- direct action methods for backward compatibility --------------
    def do_greet(self):
        return "Hello! I am Maruti. How can I help you?"

    def do_exit(self):
        return "Goodbye!"

    def do_unknown(self, heard=None, **_):
        base = "Sorry, I did not understand that." if not heard else f"Sorry, '{heard}' is not recognized."
        return f"{base} Supported commands include: 'open <app>', 'open google.com', 'search <query>', 'type <text>', 'scroll up/down', 'volume <level>', or 'help'."

    def do_open(self, kind, target, label):
        if self.context:
            if kind == "site":
                valid, target_url, netloc = self.registry.system.validate_url(target)
                site_name = "youtube" if "youtube" in (netloc or target).lower() else (netloc or target)
                self.context.update_site(site_name, target_url or target, page_state="homepage")
            else:
                self.context.update_app(target)
                if target in ("notepad", "gnome-text-editor", "gedit", "kate", "mousepad", "text editor", "document"):
                    self.context.active_editor = "gnome-text-editor"
        if self.dry_run:
            return f"Opening {label}."
        if kind == "app":
            ok, msg = self.registry.system.open_application(target)
            return msg
        else:
            ok, msg = self.registry.browser.open_website(target)
            return msg

    def do_open_folder(self, folder: str):
        if self.dry_run:
            return f"Opening {folder} folder."
        ok, msg = self.registry.system.open_folder(folder)
        return msg

    def do_web_search(self, query):
        if self.context:
            url = f"https://www.google.com/search?q={quote_plus(query)}"
            self.context.update_site("google", url, page_state="search_results")
            self.context.update_search(query, site="google")
        if self.dry_run:
            return f"Searching for {query}."
        ok, msg = self.registry.browser.search_web(query)
        return msg

    def do_youtube(self, query="", play=False):
        if self.context:
            if query:
                self.context.update_site("youtube", f"https://www.youtube.com/results?search_query={quote_plus(query)}", "search_results")
                self.context.update_search(query, "youtube")
            else:
                self.context.update_site("youtube", "https://www.youtube.com", "homepage")
        if self.dry_run:
            if play and query:
                return f"Playing {query} on YouTube."
            return f"Showing YouTube results for {query}." if query else "Opening YouTube."
        if not query:
            return self.registry.browser.open_website("https://www.youtube.com")[1]
        ok, msg = self.registry.browser.search_youtube(query)
        if play:
            # If safe OCR perception is available, locate and click the first video
            if self.registry.perception.is_ocr_available():
                time.sleep(0.5)
                ok_click, _ = self.registry.browser.click_first_video()
                if ok_click:
                    return f"Playing {query} on YouTube."
            return f"Showing YouTube results for {query}. Please select a video to play."
        return msg

    def do_volume_set(self, percent: float):
        if self.dry_run:
            return f"Volume set to {int(percent)} percent."
        ok, msg = self.registry.audio.set_volume(percent)
        return msg

    def do_volume_change(self, delta: float):
        if self.dry_run:
            action = "increased" if delta > 0 else "lowered"
            return f"Volume {action} by {abs(int(delta))} percent."
        ok, msg = self.registry.audio.change_volume(delta)
        return msg

    def do_volume_mute(self, state: bool):
        if self.dry_run:
            return "Audio muted." if state else "Audio unmuted."
        ok, msg = self.registry.audio.set_mute(state)
        return msg

    def do_type_text(self, text: str, newline: bool = False):
        if self.context:
            self.context.record_text_input(text, newline=newline)
        if self.dry_run:
            return "Typed."
        return self.registry.input.type_text(text, newline=newline)[1]

    def do_press_keys(self, keys):
        if not keys:
            return "No keys specified."
        # Intercept and route common editing shortcuts to maintain synchronized state
        if keys == ["ctrl", "a"]:
            return self.do_select_all()
        elif keys == ["ctrl", "c"]:
            return self.do_clipboard_copy()
        elif keys == ["ctrl", "x"]:
            return self.do_clipboard_cut()
        elif keys == ["ctrl", "v"]:
            return self.do_clipboard_paste()
        elif keys == ["ctrl", "z"]:
            return self.do_edit_undo()
        elif keys in (["ctrl", "y"], ["ctrl", "shift", "z"]):
            return self.do_edit_redo()
        elif keys == ["ctrl", "s"]:
            return self.do_save_file()
        elif keys == ["enter"]:
            if self.context:
                self.context.record_newline()
            if self.dry_run:
                return "Pressed enter."
            return self.registry.input.press_key("enter")[1]
        elif keys in (["backspace"], ["delete"]):
            return self.do_delete_selected()

        if self.dry_run:
            return "Pressed " + " plus ".join(keys) + "."
        return self.registry.input.press_keys(keys)[1]

    def do_select_all(self):
        if self.context:
            self.context.record_selection("all")
        if self.dry_run:
            return "Selected all."
        return self.registry.input.select_all()[1]

    def do_select_line(self, line_number: Optional[int] = None):
        if self.context:
            buf_len = len(self.context.editor_buffer)
            if line_number is not None and line_number > buf_len and buf_len > 0:
                return f"Document only has {buf_len} lines, cannot select line {line_number}."
            elif line_number is not None and buf_len == 0:
                self.context.record_selection("line", line_number=line_number)
                return "Document is empty."
            self.context.record_selection("line", line_number=line_number)
        if self.dry_run:
            return f"Selected line {line_number}." if line_number is not None else "Selected current line."
        return self.registry.input.select_line(line_number)[1]

    def do_select_word(self, direction: str = "current"):
        if self.context:
            self.context.record_selection("word")
        if self.dry_run:
            return f"Selected {direction} word."
        return self.registry.input.select_word(direction)[1]

    def do_select_to_boundary(self, boundary: str = "line_end"):
        if self.dry_run:
            return f"Selected to {boundary}."
        return self.registry.input.select_to_boundary(boundary)[1]

    def do_clear_selection(self):
        if self.context:
            self.context.selected_text = None
        if self.dry_run:
            return "Selection cleared."
        return self.registry.input.clear_selection()[1]

    def do_move_cursor(self, direction: str = "left", steps: int = 1):
        if self.context:
            if direction == "left":
                self.context.cursor_col = max(0, self.context.cursor_col - steps)
            elif direction == "right":
                self.context.cursor_col += steps
            elif direction == "up":
                self.context.cursor_line = max(0, self.context.cursor_line - steps)
            elif direction == "down":
                self.context.cursor_line = min(max(0, len(self.context.editor_buffer) - 1), self.context.cursor_line + steps)
        if self.dry_run:
            return f"Moved cursor {direction}."
        return self.registry.input.move_cursor(direction, steps)[1]

    def do_go_to_boundary(self, boundary: str = "doc_end"):
        if self.context:
            b_clean = boundary.lower().strip()
            if b_clean in ("doc_start", "beginning of document", "start of document", "top of document"):
                self.context.cursor_line = 0
                self.context.cursor_col = 0
            elif b_clean in ("doc_end", "end of document", "bottom of document"):
                self.context.cursor_line = max(0, len(self.context.editor_buffer) - 1)
                self.context.cursor_col = len(self.context.editor_buffer[-1]) if self.context.editor_buffer else 0
            elif b_clean in ("line_start", "beginning of line"):
                self.context.cursor_col = 0
            elif b_clean in ("line_end", "end of line"):
                if 0 <= self.context.cursor_line < len(self.context.editor_buffer):
                    self.context.cursor_col = len(self.context.editor_buffer[self.context.cursor_line])
        if self.dry_run:
            return f"Moved to {boundary}."
        return self.registry.input.go_to_boundary(boundary)[1]

    def do_clipboard_copy(self):
        if self.dry_run:
            if self.context:
                self.context.record_clipboard_copy()
            return "Copied."
        ok, msg = self.registry.input.clipboard_copy()
        if self.context:
            from core.clipboard import get_clipboard_text
            val = get_clipboard_text()
            self.context.record_clipboard_copy(val or None)
        return "Copied."

    def do_clipboard_cut(self):
        if self.dry_run:
            if self.context:
                self.context.record_clipboard_cut()
            return "Cut."
        ok, msg = self.registry.input.clipboard_cut()
        if self.context:
            from core.clipboard import get_clipboard_text
            val = get_clipboard_text()
            if val:
                self.context.selected_text = val
            self.context.record_clipboard_cut()
        return "Cut."

    def do_clipboard_paste(self):
        if self.dry_run:
            if self.context:
                self.context.record_clipboard_paste()
            return "Pasted."
        ok, msg = self.registry.input.clipboard_paste()
        if self.context:
            from core.clipboard import get_clipboard_text
            val = get_clipboard_text()
            self.context.record_clipboard_paste(val or None)
        return "Pasted."

    def do_edit_undo(self):
        if self.context:
            self.context.record_undo()
        if self.dry_run:
            return "Undone."
        return self.registry.input.edit_undo()[1]

    def do_edit_redo(self):
        if self.context:
            self.context.record_redo()
        if self.dry_run:
            return "Redone."
        return self.registry.input.edit_redo()[1]

    def do_delete_selected(self):
        if self.context:
            self.context.record_clipboard_cut()
        if self.dry_run:
            return "Deleted."
        return self.registry.input.delete_selected()[1]

    def do_find_text(self, query: Optional[str] = None):
        if self.dry_run:
            return f"Finding {query}." if query else "Opened find dialog."
        return self.registry.input.find_text(query)[1]

    def do_replace_text(self, find_query: Optional[str] = None, replace_query: Optional[str] = None):
        if self.dry_run:
            return "Opened replace dialog."
        return self.registry.input.replace_text(find_query, replace_query)[1]

    def do_save_file(self):
        if self.dry_run:
            return "Saved file."
        return self.registry.input.save_file()[1]

    def do_save_file_as(self, file_path: Optional[str] = None):
        if file_path and os.path.exists(file_path):
            if not self.confirm(f"File '{file_path}' already exists. Overwrite?"):
                return "Save cancelled to prevent overwrite."
        if self.dry_run:
            return "Opened save as dialog."
        return self.registry.input.save_file_as()[1]

    def do_open_and_type(self, app: str = "notepad", text: str = ""):
        self.do_open("app", app, app)
        time.sleep(1.2)
        self.do_type_text(text)
        return f"Opened {app} and typed: {text}"

    def do_caps(self, state):
        if self.dry_run:
            return f"Caps lock {state}."
        self.registry.input.press_keys(["capslock"])
        return f"Caps lock {state}."

    def do_scroll(self, direction, amount=None, qualifier=None, repetitions=1):
        if self.dry_run:
            return f"Scrolling {direction}."
        return self.registry.input.scroll(
            direction=direction,
            amount=amount,
            qualifier=qualifier,
            repetitions=repetitions,
        )[1]

    def do_nav(self, direction):
        if self.dry_run:
            return f"Going {direction}."
        keys = ["alt", "right" if direction == "forward" else "left"]
        return self.registry.input.press_keys(keys)[1]

    def do_new_tab(self):
        if self.dry_run:
            return "Opened a new tab."
        return self.registry.input.press_keys(["ctrl", "t"])[1]

    def do_close_tab(self):
        if self.dry_run:
            return "Closed the tab."
        return self.registry.input.press_keys(["ctrl", "w"])[1]

    def do_minimize(self):
        if self.dry_run:
            return "Window minimized."
        return self.registry.input.press_keys(["win", "down"])[1]

    def do_close_window(self):
        if not self.confirm("Do you want me to close the current window?"):
            return "Okay, I did not close it."
        if self.dry_run:
            return "Window closed."
        return self.registry.input.press_keys(["alt", "f4"])[1]

    def do_switch_window(self):
        if self.dry_run:
            return "Switched the window."
        res = self.registry.input.press_keys(["alt", "tab"])
        time.sleep(0.2)
        if self.context:
            self.context.sync_desktop_state()
            target = self.context.current_site or self.context.target_app
            if target:
                return f"Switched to {target}."
        return res[1]

    def do_start_dictation(self):
        if self.context:
            self.context.is_dictation_mode = True
        return "Dictation mode started. Speak freely, and say 'stop dictation' when finished."

    def do_stop_dictation(self):
        if self.context:
            self.context.is_dictation_mode = False
        return "Dictation mode stopped."

    def do_hello_world(self):
        if self.dry_run:
            return "I wrote a simple hello world program in Notepad."
        return self.registry._handle_hello_world()

    def do_weather(self, city):
        return self.registry._handle_weather(city)

    def do_chat(self, question):
        return self.brain.ask(question) if self.brain else "AI brain is not available."

    def do_click(self, label):
        if self.dry_run:
            return f"[dry-run] would click on {label}."
        return self.registry.browser.click_element_by_label(label)[1]

    def do_browser_click_video(self, index=1):
        ordinal = "first" if index == 1 else "second" if index == 2 else f"number {index}"
        if self.context:
            self.context.page_state = "watch"
            self.context.update_action(f"click_video_{index}", f"Clicked the {ordinal} video.")
        if self.dry_run:
            return f"Clicked the {ordinal} video."
        return self.registry.browser.click_video(index)[1]

    def do_media_pause(self):
        if self.context:
            self.context.update_media_state("paused")
            self.context.update_action("media_pause", "Video paused.")
        if self.dry_run:
            return "Video paused."
        return self.registry.browser.pause_media()[1]

    def do_media_resume(self):
        if self.context:
            self.context.update_media_state("playing")
            self.context.update_action("media_resume", "Video resumed.")
        if self.dry_run:
            return "Video resumed."
        return self.registry.browser.resume_media()[1]

    def do_read_screen(self):
        return self.registry.perception.read_visible_text()

    def do_inspect_screen(self):
        return self.registry.perception.describe_screen()
