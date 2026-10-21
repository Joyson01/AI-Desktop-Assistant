"""Central Action Registry for MARUTI Desktop Assistant.

Defines schemas, risk ratings, verification strategies, and handlers
for all supported desktop actions.
Integrates system control, audio, input, perception, browser, and conversation brain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

from core.audio import AudioController
from core.browser import BrowserAutomation
from core.context import ConversationContext
from core.input import DesktopInputBackend
from core.perception import PerceptionEngine
from core.policy import ActionRisk, ActionResult, PolicyEngine
from core.system_control import SystemController

logger = logging.getLogger("maruti.action_registry")


@dataclass
class ActionDefinition:
    """Metadata and execution specification for a desktop action."""
    name: str
    description: str
    handler: Callable[..., str]
    risk: ActionRisk = ActionRisk.SAFE
    timeout_sec: float = 10.0
    confirmation_prompt: Optional[str] = None
    verification_strategy: str = "exit_code_or_state"


class CentralActionRegistry:
    """Manages and executes all registered desktop actions under policy constraints."""

    def __init__(
        self,
        brain: Any = None,
        dry_run: bool = False,
        confirm_callback: Optional[Callable[[str], bool]] = None,
        context: Optional[ConversationContext] = None,
    ) -> None:
        self.brain = brain
        self.dry_run = dry_run
        self.context = context or ConversationContext()
        self.policy = PolicyEngine(confirm_callback=confirm_callback)
        self.audio = AudioController()
        self.input = DesktopInputBackend()
        self.system = SystemController()
        self.perception = PerceptionEngine()
        self.browser = BrowserAutomation(
            system_controller=self.system,
            input_backend=self.input,
            perception=self.perception,
            policy=self.policy,
            context=self.context,
        )

        self._actions: Dict[str, ActionDefinition] = {}
        self._register_default_actions()
        logger.info("CentralActionRegistry initialized with %d actions (dry_run=%s)", len(self._actions), self.dry_run)

    def register(self, action: ActionDefinition) -> None:
        """Register an action definition."""
        self._actions[action.name] = action

    def get_action(self, name: str) -> Optional[ActionDefinition]:
        """Retrieve action definition by intent name."""
        return self._actions.get(name)

    def dispatch(self, intent_name: str, args: Dict[str, Any]) -> ActionResult:
        """Execute action through policy validation and return an ActionResult."""
        action = self._actions.get(intent_name)
        if not action:
            logger.warning("Unregistered intent requested: '%s'", intent_name)
            return ActionResult(
                success=False,
                message="I don't know how to do that yet.",
                error=f"Unknown intent: {intent_name}",
            )

        # 1. Safety Policy Gate
        if action.risk == ActionRisk.SENSITIVE:
            prompt = action.confirmation_prompt or f"Are you sure you want to perform '{intent_name}'?"
            confirmed = self.policy.authorize_execution(intent_name, args, custom_prompt=prompt)
            if not confirmed:
                return ActionResult(
                    success=False,
                    message="Action cancelled.",
                    data={"intent": intent_name, "cancelled": True},
                )

        # 2. Execution
        try:
            spoken_message = action.handler(**args)
            return ActionResult(
                success=True,
                message=spoken_message,
                data={"intent": intent_name, "args": args, "dry_run": self.dry_run},
            )
        except Exception as exc:
            logger.exception("Error executing action '%s'", intent_name)
            return ActionResult(
                success=False,
                message=f"Sorry, that failed: {exc}",
                error=str(exc),
            )

    def _register_default_actions(self) -> None:
        """Populate the registry with all standard MARUTI desktop actions."""

        # 1. Greetings & System
        self.register(ActionDefinition(
            name="greet",
            description="Respond to greeting",
            handler=lambda: "Hello! I am Maruti. How can I help you?",
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="exit",
            description="Exit assistant session",
            handler=lambda: "Goodbye! Have a productive day.",
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="unknown",
            description="Handle unrecognized command",
            handler=lambda **_: "Sorry, I did not catch that clearly. Could you please rephrase?",
            risk=ActionRisk.SAFE,
        ))

        # 2. Application, Folder, URL launches
        def handle_open(kind: str, target: str, label: str):
            if self.dry_run:
                return f"Opening {label}."
            if kind == "app":
                ok, msg = self.system.open_application(target)
                return msg
            elif kind == "site":
                ok, msg = self.browser.open_website(target)
                return msg
            return f"Opening {label}."

        self.register(ActionDefinition(
            name="open",
            description="Open an allowlisted application or website",
            handler=handle_open,
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="open_folder",
            description="Open an allowlisted user directory",
            handler=lambda folder: self.system.open_folder(folder)[1],
            risk=ActionRisk.SAFE,
        ))

        # 3. System Volume
        self.register(ActionDefinition(
            name="volume_set",
            description="Set master volume to an exact percentage",
            handler=lambda percent: self.audio.set_volume(percent)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="volume_change",
            description="Adjust master volume by a relative percentage",
            handler=lambda delta: self.audio.change_volume(delta)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="volume_mute",
            description="Mute or unmute master volume",
            handler=lambda state: self.audio.set_mute(state)[1],
            risk=ActionRisk.SAFE,
        ))

        # 4. Desktop Input & Scrolling
        self.register(ActionDefinition(
            name="scroll",
            description="Perform bounded scrolling",
            handler=lambda direction, amount=None, qualifier=None, repetitions=1: (
                self.input.scroll(direction, amount=amount, qualifier=qualifier, repetitions=repetitions)[1]
            ),
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="type_text",
            description="Type text via keyboard or clipboard",
            handler=lambda text: self.input.type_text(text)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="press_keys",
            description="Press key shortcut combo",
            handler=lambda keys: self.input.press_keys(keys)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="caps",
            description="Toggle or set caps lock",
            handler=lambda state="toggle": self._handle_caps(state),
            risk=ActionRisk.SAFE,
        ))

        # 5. Browser & Navigation
        self.register(ActionDefinition(
            name="nav",
            description="Browser forward or back",
            handler=lambda direction: self.input.press_keys(["alt", "right" if direction == "forward" else "left"])[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="new_tab",
            description="Open new browser tab",
            handler=lambda: self.input.press_keys(["ctrl", "t"])[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="close_tab",
            description="Close current browser tab",
            handler=lambda: self.input.press_keys(["ctrl", "w"])[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="minimize",
            description="Minimize active window",
            handler=lambda: self.input.press_keys(["win", "down"])[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="switch_window",
            description="Switch to next window",
            handler=lambda: self.input.press_keys(["alt", "tab"])[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="close_window",
            description="Close active window",
            handler=lambda: self.input.press_keys(["alt", "f4"])[1],
            risk=ActionRisk.SENSITIVE,
            confirmation_prompt="Do you want me to close the current window?",
        ))

        self.register(ActionDefinition(
            name="web_search",
            description="Search the web using Google",
            handler=lambda query: self.browser.search_web(query)[1],
            risk=ActionRisk.SAFE,
        ))

        def handle_youtube(query: str = "", play: bool = False):
            if not query:
                return self.browser.open_website("https://www.youtube.com")[1]
            ok, msg = self.browser.search_youtube(query)
            if play:
                time.sleep(0.4)
                self.browser.click_first_video()
                return f"Playing {query} on YouTube."
            return msg

        self.register(ActionDefinition(
            name="youtube",
            description="Search YouTube or play video",
            handler=handle_youtube,
            risk=ActionRisk.SAFE,
        ))

        # 6. Perception & Visual Click
        self.register(ActionDefinition(
            name="click",
            description="Locate text target via OCR and click",
            handler=lambda label: self.browser.click_element_by_label(label)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="read_screen",
            description="Read visible screen text",
            handler=lambda: self.perception.read_visible_text(),
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="inspect_screen",
            description="Summarize what is on the screen",
            handler=lambda: self.perception.describe_screen(),
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="browser_click_video",
            description="Click a video result by 1-based index",
            handler=lambda index=1: self.browser.click_video(index)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="media_pause",
            description="Pause active video or audio playback",
            handler=lambda: self.browser.pause_media()[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="media_resume",
            description="Resume active video or audio playback",
            handler=lambda: self.browser.resume_media()[1],
            risk=ActionRisk.SAFE,
        ))

        # 7. Utilities & Conversation Brain
        self.register(ActionDefinition(
            name="weather",
            description="Fetch weather for a city",
            handler=self._handle_weather,
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="chat",
            description="Answer questions via Gemini Brain",
            handler=lambda question: (self.brain.ask(question) if self.brain else "AI brain is not available."),
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="hello_world",
            description="Open notepad and type hello world",
            handler=self._handle_hello_world,
            risk=ActionRisk.SAFE,
        ))

        # 8. Text Editing, Selection & Clipboard Automation
        self.register(ActionDefinition(
            name="select_all",
            description="Select all text in active document",
            handler=lambda: self.input.select_all()[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="select_line",
            description="Select specified line number or current line",
            handler=lambda line_number=None: self.input.select_line(line_number)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="select_word",
            description="Select current, next, or previous word",
            handler=lambda direction="current": self.input.select_word(direction)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="select_to_boundary",
            description="Select from cursor to document or line boundary",
            handler=lambda boundary="line_end": self.input.select_to_boundary(boundary)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="clear_selection",
            description="Clear active text selection",
            handler=lambda: self.input.clear_selection()[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="move_cursor",
            description="Move cursor in direction by steps",
            handler=lambda direction="left", steps=1: self.input.move_cursor(direction, steps)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="go_to_boundary",
            description="Move cursor to document or line boundary",
            handler=lambda boundary="doc_end": self.input.go_to_boundary(boundary)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="clipboard_copy",
            description="Copy selection to clipboard",
            handler=lambda: self.input.clipboard_copy()[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="clipboard_cut",
            description="Cut selection to clipboard",
            handler=lambda: self.input.clipboard_cut()[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="clipboard_paste",
            description="Paste text from clipboard",
            handler=lambda: self.input.clipboard_paste()[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="edit_undo",
            description="Undo last edit",
            handler=lambda: self.input.edit_undo()[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="edit_redo",
            description="Redo last undone edit",
            handler=lambda: self.input.edit_redo()[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="delete_selected",
            description="Delete selected text or backspace",
            handler=lambda: self.input.delete_selected()[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="find_text",
            description="Open find dialog and search for text",
            handler=lambda query=None: self.input.find_text(query)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="replace_text",
            description="Open replace dialog",
            handler=lambda find_query=None, replace_query=None: self.input.replace_text(find_query, replace_query)[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="save_file",
            description="Save active document",
            handler=lambda: self.input.save_file()[1],
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="save_file_as",
            description="Save document with confirmation if overwriting",
            handler=lambda: self.input.save_file_as()[1],
            risk=ActionRisk.SENSITIVE,
            confirmation_prompt="Do you want to save this document with a new name?",
        ))

        self.register(ActionDefinition(
            name="open_and_type",
            description="Launch editor and type initial text",
            handler=lambda app="notepad", text="": self._handle_open_and_type(app, text),
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="start_dictation",
            description="Start hands-free dictation mode",
            handler=lambda: self._handle_start_dictation(),
            risk=ActionRisk.SAFE,
        ))

        self.register(ActionDefinition(
            name="stop_dictation",
            description="Stop hands-free dictation mode",
            handler=lambda: self._handle_stop_dictation(),
            risk=ActionRisk.SAFE,
        ))

    def _handle_start_dictation(self) -> str:
        if self.context:
            self.context.is_dictation_mode = True
        return "Dictation mode started. Speak freely, and say 'stop dictation' when finished."

    def _handle_stop_dictation(self) -> str:
        if self.context:
            self.context.is_dictation_mode = False
        return "Dictation mode stopped."

    def _handle_caps(self, state: str) -> str:
        self.input.press_keys(["capslock"])
        return f"Caps lock {state}."

    def _handle_weather(self, city: str) -> str:
        import requests
        from urllib.parse import quote_plus
        try:
            r = requests.get(
                f"https://wttr.in/{quote_plus(city)}",
                timeout=6,
                params={"format": "%l: %C, %t, humidity %h, wind %w"},
            )
            r.raise_for_status()
            return r.text.strip()
        except Exception as exc:
            return f"Could not fetch weather for {city}: {exc}"

    def _handle_hello_world(self) -> str:
        self.system.open_application("notepad")
        import time
        time.sleep(1.2)
        self.input.type_text('print("Hello, World!")')
        return "I wrote a simple hello world program in Notepad."

    def _handle_open_and_type(self, app: str = "notepad", text: str = "") -> str:
        self.system.open_application(app)
        import time
        time.sleep(1.2)
        self.input.type_text(text)
        return f"Opened {app} and typed: {text}"
