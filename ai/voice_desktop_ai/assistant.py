import os

# Prevent Snap environments (e.g. VS Code / Antigravity terminal) from leaking mismatched schemas
os.environ.pop("GSETTINGS_SCHEMA_DIR", None)
if "XDG_DATA_DIRS" in os.environ and "snap/code" in os.environ["XDG_DATA_DIRS"]:
    _cleaned_dirs = [d for d in os.environ["XDG_DATA_DIRS"].split(":") if "snap/code" not in d]
    os.environ["XDG_DATA_DIRS"] = ":".join(_cleaned_dirs) or "/usr/local/share/:/usr/share/:/var/lib/snapd/desktop"

os.environ.setdefault("QT_QPA_PLATFORMTHEME", "xdgdesktopportal")
os.environ.setdefault("QT_STYLE_OVERRIDE", "Fusion")

import re
import time

try:
    import pyautogui
except Exception:
    pyautogui = None

from actions.engine import execute
from brain.context import Context
from brain.conversation import ConversationManager, default_conversation_provider
from brain.gemini_client import GeminiClient
from brain.intent import Intent, parse_intent
from brain.intent_router import AMBIGUOUS, COMPUTER_ACTION, CONVERSATION, MIXED, WEB_NAVIGATION, IntentRouter
from brain.llm import LLMBrain
from brain.memory import Memory
from brain.planner import make_plan
from brain.providers.grok_visual_brain import GrokVisualBrain
from brain.providers.provider_config import load_provider_config
from brain.smart_brain import SmartBrain
from brain.web_resolver import WebResolver
from computer.action_executor import ActionExecutor
from perception.observer import observe_screen
from perception.uia import find_target, perform
import tts
from verification.verifier import state_valid
from voice.stt import SpeechService


MAX_RETRIES = 2


def speak(message):
    tts.speak(message)


class AccessibilityAssistant:
    def __init__(self, dry_run=None, conversation_provider=None):
        self.dry_run = os.environ.get("VOICE_ASSISTANT_DRY_RUN") == "1" if dry_run is None else dry_run
        self.speech = SpeechService()
        provider = default_conversation_provider() if conversation_provider is None else conversation_provider
        self.conversation = ConversationManager(provider=provider)
        self.router = IntentRouter()
        self.intent_router = self.router
        self.smart_brain = SmartBrain(router=self.router, conversation=self.conversation)
        self.memory = Memory()
        self.context = Context()
        self.brain = LLMBrain()
        self.action_executor = ActionExecutor()
        provider_config = load_provider_config()
        self.grok_live = os.environ.get("MARUTI_GROK_LIVE") == "1" and provider_config.configured
        self.grok_orchestrator = None
        self.grok_brain = GrokVisualBrain(api_key=provider_config.api_key, model=provider_config.model) if self.grok_live else None
        website_provider = self.conversation.provider or GeminiClient()
        self.web_resolver = WebResolver(
            gemini=website_provider,
            grok=self.grok_brain if self.grok_live else None,
        )
        self.state = None
        self.last_transcript = ""
        self.last_transcript_at = 0.0
        self.type_mode = False
        self.pending_confirmation = None

    def observe(self, include_fallback=False, target=None):
        self.state = observe_screen(include_fallback, target=target)
        self.context.application = self.state.active_application
        self.context.window_title = self.state.active_window
        return self.state

    def resolve(self, target, role=""):
        if target in {"it", "that", "this", "the selected one"} and self.context.last_target:
            return self.context.last_target
        state = self.state or self.observe(include_fallback=True)
        return find_target(
            target,
            role,
            state.ui_elements,
            screenshot=state.screenshot,
            visual_candidates=state.visual_candidates,
            context={
                "active_app": getattr(state, "active_application", ""),
                "current_url": getattr(state, "active_window", ""),
                "previous_command": self.last_transcript,
                "recent_targets": [self.context.last_target] if self.context.last_target else [],
                "screen_region": "active_window",
            },
        )

    def understand_screen(self, request):
        state = self.state or self.observe(include_fallback=True)
        return self.brain.understand_screen(request, {
            "active_window": state.active_window,
            "ui_elements": [
                {
                    "name": element.name,
                    "control_type": element.control_type,
                    "automation_id": element.automation_id,
                    "rectangle": element.rectangle,
                    "enabled": element.enabled,
                    "visible": element.visible,
                    "patterns": element.patterns,
                }
                for element in state.ui_elements
            ],
            "visual_candidates": state.visual_candidates,
        })

    def execute_step(self, intent):
        started = time.perf_counter()
        element = None
        needs_target_resolution = intent.action in {"click", "double_click", "right_click"}
        before = self.state
        if before is None or (needs_target_resolution and getattr(before, "screenshot", None) is None):
            before = self.observe(include_fallback=needs_target_resolution, target=intent.target if needs_target_resolution else None)
        if needs_target_resolution:
            resolve_started = time.perf_counter()
            element = self.resolve(intent.target, getattr(intent, "role", ""))
            print(f"[PERF] target_resolution={(time.perf_counter() - resolve_started) * 1000:.1f}ms")
            if element:
                self.context.remember_target(element)
        result = execute(
            intent,
            before,
            lambda: self.state,
            self.resolve,
            perform,
            dry_run=self.dry_run,
            resolved_element=element,
        )
        if result.success and result.verified:
            print(f"[PERF] verification=0.0ms")
            print(f"[PERF] total={(time.perf_counter() - started) * 1000:.1f}ms")
            return True
        if result.message == "target not found":
            print("[CLICK] target resolution failed; retry skipped")
            return False
        for attempt in range(MAX_RETRIES):
            retry_started = time.perf_counter()
            self.observe()
            retry_element = None
            if intent.action in {"click", "double_click", "right_click"}:
                retry_element = self.resolve(intent.target, getattr(intent, "role", ""))
            result = execute(
                intent,
                self.state,
                lambda: self.state,
                self.resolve,
                perform,
                dry_run=self.dry_run,
                resolved_element=retry_element,
            )
            if result.success and result.verified:
                print(f"[PERF] verification={(time.perf_counter() - retry_started) * 1000:.1f}ms")
                print(f"[PERF] total={(time.perf_counter() - started) * 1000:.1f}ms")
                return True
            print(f"Retry {attempt + 1}/{MAX_RETRIES}: {result.message}")
        print(f"[PERF] verification={(time.perf_counter() - started) * 1000:.1f}ms")
        print(f"[PERF] total={(time.perf_counter() - started) * 1000:.1f}ms")
        return False

    def handle(self, transcript, direct_command=False):
        normalized = " ".join(str(transcript or "").lower().split())
        now = time.monotonic()
        if normalized == self.last_transcript and now - self.last_transcript_at < 1.0:
            return True
        self.last_transcript, self.last_transcript_at = normalized, now
        print(f"You said: {transcript}")
        if self.pending_confirmation:
            pending = self.pending_confirmation
            self.pending_confirmation = None
            if normalized in {"yes", "haan", "han", "हाँ", "हां"}:
                if pending == "shutdown" and self.execute_step(Intent("shutdown")):
                    return True
                if pending == "close_window" and self._execute_structured({"action": "hotkey", "keys": ["alt", "f4"]}):
                    return True
            speak("Shutdown cancelled." if pending == "shutdown" else "Action cancelled.")
            return True
        addressed_to_maruti = direct_command or bool(re.search(r"\bmaruti\b", normalized))
        intent_started = time.perf_counter()
        route = self.router.route(transcript)
        print(f"[PERF] intent_parse={(time.perf_counter() - intent_started) * 1000:.1f}ms")
        if route.route == CONVERSATION and not addressed_to_maruti:
            return True
        if route.route in {AMBIGUOUS, MIXED} and not route.clarification:
            return True
        simple_click = route.route == COMPUTER_ACTION and route.semantic_intent in {
            "click_visual_target", "right_click",
        }
        if not simple_click:
            self.smart_brain.use_route(route)
        decision = None if simple_click else self.smart_brain.decide(transcript, memory=self.memory)
        if decision is not None and decision.mode == "web_media" and route.route != WEB_NAVIGATION:
            if self.grok_live and any(word in normalized for word in ("open", "kholo", "search")):
                grok_result = self._handle_grok(transcript)
                if grok_result is not None:
                    return grok_result
            return self.handle_media_request(decision)
        intent = parse_intent(normalized)
        if intent and intent.action in {"start_type_mode", "end_type_mode"} and not addressed_to_maruti:
            speak("Please say Maruti for typing mode.")
            return True
        if intent and intent.action == "start_type_mode" and addressed_to_maruti:
            self.type_mode = True
            print("Typing mode activated. Speech responses are muted.")
            return True
        if intent and intent.action == "end_type_mode" and self.type_mode and addressed_to_maruti:
            self.type_mode = False
            speak("Type mode off.")
            return True
        if self.type_mode:
            intent = Intent("type", value=transcript)
            return self.execute_step(intent)
        if route.route == CONVERSATION:
            if route.semantic_intent in {"hello", "how_are_you"}:
                speak(self.conversation.respond(Intent(route.semantic_intent)))
            else:
                speak(self.conversation.answer(transcript, route=route))
            return True
        if route.route == WEB_NAVIGATION:
            target = route.metadata.get("target", "")
            if not target:
                speak("Which website should I open?")
                return True
            result = self.web_resolver.resolve_website(target)
            if not result:
                speak("I couldn't resolve that official website.")
                return True
            if not self.dry_run and not self._execute_structured({"action": "open_url", "target": result.url}):
                return True
            print(f"[WEB] target={target} opened_url={result.url}")
            speak("Opening.")
            return True
        if route.route in {AMBIGUOUS, MIXED}:
            speak(route.clarification)
            return True
        if self.grok_live and route.route == COMPUTER_ACTION and not simple_click:
            grok_result = self._handle_grok(transcript)
            if grok_result is not None:
                return grok_result
        if route.route == COMPUTER_ACTION and route.legacy_intent is not None:
            intent = route.legacy_intent
        if route.semantic_intent == "open_chrome":
            intent = Intent("open", target="chrome")
        if route.semantic_intent == "shutdown":
            self.pending_confirmation = "shutdown"
            speak("Are you sure you want to shut down the computer?")
            return True
        if route.semantic_intent == "close_window":
            self.pending_confirmation = "close_window"
            speak("Are you sure you want to close the current window?")
            return True
        structured_action = self._structured_action(route)
        if structured_action is not None:
            if self._execute_structured(structured_action):
                speak("Okay, done.")
            return True
        if intent is None:
            speak("I didn't understand that.")
            return True
        if intent.action in {"hello", "how_are_you", "remember_name", "recall_name"}:
            speak(self.conversation.respond(intent))
            return True
        if intent.action == "screen_query":
            self.observe(include_fallback=True)
            target = self.resolve(intent.target, intent.role)
            analysis = self.understand_screen(transcript)
            if not target and analysis.get("understood"):
                target = analysis.get("targets", [None])[0]
            if target:
                self.context.remember_target(target)
                speak(f"Yes, I can see {intent.target}.")
            else:
                speak("I can't find that on the screen.")
            return True
        self.observe()
        if self.type_mode:
            return self.execute_step(intent)
        plan = make_plan(intent)
        for step in plan.steps:
            if step.action == "exit":
                speak("Okay, goodbye.")
                return False
            if step.action in {"click", "double_click", "right_click", "select"}:
                target = self.resolve(step.target, step.role)
                if target:
                    self.context.remember_target(target)
                elif step.target in {"it", "that", "this"}:
                    speak("I need a previous target first.")
                    return True
            if not self.execute_step(step):
                speak("I tried, but I couldn't confirm that action.")
                return True
        speak("Okay, done.")
        return True

    def handle_media_request(self, decision):
        query = str(getattr(decision, "query", "") or "")
        print(f"[MEDIA] Query: {query}")
        if not query:
            goal = str(getattr(decision, "goal", "")).lower()
            if "youtube" in goal:
                url = "https://www.youtube.com/"
                if self.web_resolver.open_url(url):
                    speak("Opening YouTube.")
                    return True
            speak("Which song or video should I open?")
            return True
        result = self.web_resolver.resolve_youtube(query)
        print(f"[MEDIA] URL: {result.url if result else 'none'}")
        print(f"[MEDIA] Confidence: {result.confidence if result else 0}")
        if not result or not self.web_resolver.open_url(result.url):
            speak("I couldn't find that YouTube search.")
            return True
        self.memory.remember_query(query)
        self.memory.remember_result(result)
        speak(f"Opening YouTube for {query}.")
        return True

    @staticmethod
    def _structured_action(route):
        metadata = route.metadata if isinstance(route.metadata, dict) else {}
        if route.semantic_intent == "open_chrome":
            return None
        if route.semantic_intent == "select_all":
            return {"action": "select"}
        if route.semantic_intent in {"copy", "paste"}:
            return {"action": route.semantic_intent}
        if route.semantic_intent == "open_tab":
            return {"action": "hotkey", "keys": ["ctrl", "t"]}
        if route.semantic_intent == "close_tab":
            return {"action": "hotkey", "keys": ["ctrl", "w"]}
        if route.route == "system_control":
            return {
                "action": "system_control",
                "target": metadata.get("system_action"),
                "operation": metadata.get("operation", "set"),
                "value": metadata.get("value"),
            }
        action = metadata.get("action")
        if action:
            payload = dict(metadata)
            payload.pop("raw_text", None)
            return payload
        return None

    def _execute_structured(self, action):
        if self.dry_run:
            return True
        result = self.action_executor.execute(action)
        if not result.get("success"):
            print(f"[ERROR] component=action_executor message={result.get('message', 'unknown error')}")
            speak("I couldn't complete that action.")
            return False
        return True

    def _handle_grok(self, goal):
        if self.grok_orchestrator is None:
            return None
        state = self.grok_orchestrator.run(goal)
        if getattr(state, "status", "") in {"completed", "failed"}:
            return True
        return None

    @staticmethod
    def _verify_grok_transition(before, after, action, result, state):
        from verification.verifier import VerificationResult
        expected_state = getattr(state, "expected_state", None)
        if result.get("success") and expected_state and getattr(after, "state", None) == expected_state:
            return VerificationResult("success", 1.0, "Expected state observed.", expected_state=expected_state)
        return VerificationResult("uncertain", 0.0, "Expected semantic state was not confirmed.", expected_state=expected_state)

    def run(self, interactive_text=False):
        speak("Hello Boss! Maruti is here. Bataiye, aaj main aapke liye kya kar sakta hoon?")
        self.observe()
        text_mode = interactive_text or not getattr(self.speech, "is_available", True)
        if text_mode and not interactive_text:
            print("\n[NOTE] Microphone / PyAudio not detected. Switching to interactive text mode.")
            print("Type commands below (e.g. 'maruti hello', 'who is owner of tesla', or 'exit').\n")
        while True:
            try:
                if text_mode:
                    try:
                        transcript = input("\nYou (Maruti) > ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print("\nAssistant stopped.")
                        return
                    if not transcript:
                        continue
                    if transcript.lower() in {"exit", "quit", "band karo"}:
                        speak("Goodbye Boss!")
                        return
                    if not self.handle(transcript, direct_command=True):
                        return
                else:
                    audio = self.speech.listen()
                    if audio is None:
                        if not getattr(self.speech, "is_available", True):
                            text_mode = True
                            print("\n[NOTE] Microphone became unavailable. Switching to interactive text mode.")
                            print("Type commands below (or 'exit' to quit).\n")
                            continue
                        time.sleep(0.1)
                        continue
                    transcript = self.speech.speech_to_text(audio)
                    if transcript and not self.handle(transcript):
                        return
            except KeyboardInterrupt:
                print("\nAssistant stopped by keyboard.")
                self.pending_confirmation = None
                return
            except getattr(pyautogui, "FailSafeException", type("DummyFailSafe", (Exception,), {})):
                speak("The safety stop was triggered.")
            except Exception as error:
                print(f"[ERROR] component=runtime exception={type(error).__name__}: {error}")
                speak("Sorry, I couldn't do that.")


def main():
    import sys
    gui_mode = "--gui" in sys.argv or "-g" in sys.argv
    text_mode = "--text" in sys.argv or "-t" in sys.argv
    voice_mode = "--voice" in sys.argv or "-v" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if "--help" in sys.argv or "-h" in sys.argv:
        print("MARUTI — AI Voice Controlled Desktop Assistant")
        print("\nUsage:")
        print("  python assistant.py --gui      Launch modern PySide6 GUI")
        print("  python assistant.py --text     Run interactive terminal text mode")
        print("  python assistant.py --voice    Run terminal voice listening mode")
        print("  python assistant.py --dry-run  Run with desktop actions mocked")
        return

    if gui_mode:
        from gui.app import run_gui
        return run_gui(AccessibilityAssistant(dry_run=dry_run))

    if not text_mode and not voice_mode:
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        if has_display:
            try:
                from gui.app import run_gui
                return run_gui(AccessibilityAssistant(dry_run=dry_run))
            except Exception as e:
                print(f"[NOTE] GUI could not be loaded ({e}), falling back to terminal.")

    AccessibilityAssistant(dry_run=dry_run).run(interactive_text=text_mode)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAssistant stopped by keyboard.")

