"""MARUTI - AI Powered Voice Controlled Desktop Assistant.

Entry point supporting CLI, Voice, GUI, and Diagnostic Doctor modes.
Ensures graceful degradation across Linux (Ubuntu X11) and Windows 10/11.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Optional

import config
from core.context import ConversationContext
from doctor import print_doctor_report
from voice.stt import Listener
from voice.tts import Speaker
from voice.wake import WakeDetector

from assistant import Assistant

try:
    from nlu.router import IntentRouter  # Preferred modular path (Milestone 2)
except ImportError:
    try:
        from intent_router import IntentRouter  # Legacy fallback path
    except ImportError:
        IntentRouter = None

try:
    from actions import ActionExecutor  # Legacy fallback path
    from brain import Brain
except ImportError:
    ActionExecutor = None
    Brain = None

logger = logging.getLogger("maruti")

YES_TOKENS = {"yes", "yeah", "yep", "haan", "han", "ha", "ok", "okay", "sure", "theek", "kar", "confirm"}


class MarutiApp:
    """Core MARUTI desktop assistant coordinator."""

    def __init__(
        self,
        voice_mode: bool = False,
        dry_run: bool = False,
        mute: bool = False,
        mic_index: Optional[int] = None,
        language: str = config.DEFAULT_STT_LANG,
    ) -> None:
        """Initialize assistant subsystems with unified Assistant façade."""
        self.dry_run = dry_run
        self.mute = mute
        self.mic_index = mic_index
        self.language = language

        # Single route/execute façade
        self.assistant = Assistant(
            dry_run=dry_run,
            mute=mute,
            mic_index=mic_index,
            language=language,
            confirm_callback=self.ask_yes_no,
        )

        self.speaker = self.assistant.speaker
        self.wake_detector = self.assistant.wake_detector
        self.listener: Optional[Listener] = self.assistant.listener if voice_mode and self.assistant.listener.is_available else None
        self.context = self.assistant.context
        self.router = self.assistant.router
        self.executor = self.assistant.executor

        if voice_mode and (not self.listener or not self.listener.is_available):
            logger.warning("Microphone not available. Degraded to text interaction.")
            print("\n[Notice] No active microphone detected. Audio input is disabled.")
            print("         You can still use full features using standard typing.\n")

        logger.info(
            "MARUTI initialized (Voice=%s, DryRun=%s, Mute=%s, Lang=%s)",
            self.listener is not None,
            self.dry_run,
            self.mute,
            self.language,
        )

    def ask_yes_no(self, question: str) -> bool:
        """Confirmation gate for safety-sensitive actions."""
        self.speaker.say(question, block=True)
        if self.listener and self.listener.is_available:
            print(f"[MARUTI Question]: {question} (Listening for yes/no/haan/nahi...)")
            ans, _ = self.listener.listen(timeout=4.0, phrase_time_limit=4.0)
        else:
            try:
                ans = input(f"{question} (yes/no) > ").strip()
            except (EOFError, KeyboardInterrupt):
                return False

        if not ans:
            return False
        tokens = set(ans.lower().split())
        return bool(tokens & YES_TOKENS)

    def handle_command(self, raw_input: str) -> bool:
        """Process one user request through Assistant façade. Returns False when user requests exit."""
        if not raw_input or not raw_input.strip():
            return True

        result = self.assistant.process_text(raw_input, dry_run=self.dry_run)
        print(f"[MARUTI]: {result.message}")

        if result.data.get("should_exit") or result.intent_name == "exit":
            return False
        return True

    def run_text_loop(self) -> None:
        """Interactive REPL text mode."""
        print("\n" + "=" * 65)
        print("  MARUTI Desktop Assistant - Interactive Text Mode")
        print("  Type any command (e.g., 'open chrome', 'मौसम कैसा है').")
        print("  Type 'exit' or press Ctrl+C to quit.")
        print("=" * 65 + "\n")

        while True:
            try:
                user_input = input("MARUTI [Text] > ").strip()
                if not self.handle_command(user_input):
                    break
            except (KeyboardInterrupt, EOFError):
                print("\nExiting MARUTI...")
                break

        self.shutdown()

    def run_voice_loop(self) -> None:
        """Continuous hands-free voice loop."""
        if not self.listener or not self.listener.is_available:
            print("[Warning] Cannot start voice mode without an active microphone.")
            print("          Falling back to text mode...")
            self.run_text_loop()
            return

        print("\n" + "=" * 65)
        print("  MARUTI Voice Mode Active")
        print("  Speak any command directly — no wake word needed.")
        print("  Say 'exit assistant' or 'stop listening' to quit.")
        print("  Press Ctrl+C in terminal to stop.")
        print("=" * 65 + "\n")

        self.speaker.say("Maruti is online. Microphone is ready. Listening for commands.", block=True)

        consecutive_timeouts = 0
        while True:
            try:
                print("\n[Listening for commands...]")
                phrase, conf = self.listener.listen(timeout=8.0, phrase_time_limit=10.0)

                if not phrase:
                    consecutive_timeouts += 1
                    # Only print a message every 5 timeouts to avoid spam
                    if consecutive_timeouts % 5 == 0:
                        print("[Still listening... Speak a command or say 'exit assistant' to quit.]")
                    continue

                consecutive_timeouts = 0

                # Suppress recognized speech while the assistant is actively speaking
                if self.speaker.is_speaking:
                    logger.info("Ignored speech recognized while assistant was speaking: '%s'", phrase)
                    continue

                # Suppress acoustic echo of the assistant's own recent output
                if self.speaker.last_spoken and (time.time() - self.speaker.last_spoken_time < 2.5):
                    p_norm = phrase.lower().strip()
                    s_norm = self.speaker.last_spoken.lower().strip()
                    if p_norm == s_norm or p_norm in s_norm or s_norm in p_norm:
                        logger.info("Suppressed echo of assistant voice: '%s'", phrase)
                        continue

                print(f"\n[Recognized] '{phrase}' (confidence: {conf:.2f})")

                if not self.handle_command(phrase):
                    break

            except KeyboardInterrupt:
                print("\n[Maruti] Voice listening interrupted.")
                self.speaker.say("Goodbye!", block=True)
                break
            except Exception as exc:
                logger.error("Error in voice loop: %s", exc)

        self.shutdown()

    def shutdown(self) -> None:
        """Cleanly close all voice threads and resources."""
        if self.speaker:
            self.speaker.close()


def setup_logging(verbose: bool = False) -> None:
    """Configure structured logging."""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=log_level, format=log_format, datefmt="%H:%M:%S")


def main() -> None:
    """CLI argument parsing and mode dispatcher."""
    parser = argparse.ArgumentParser(
        description="MARUTI - AI Powered Voice Controlled Desktop Assistant"
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run comprehensive system diagnostics and exit.",
    )
    parser.add_argument(
        "--list-mics",
        action="store_true",
        help="List all enumerated audio input devices and exit.",
    )
    parser.add_argument(
        "--mic",
        type=int,
        default=None,
        help="Select specific microphone device index.",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Run in interactive CLI text mode (default).",
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Run in hands-free voice loop mode.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch PySide6 Graphical User Interface.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate desktop actions without making OS modifications.",
    )
    parser.add_argument(
        "--mute",
        action="store_true",
        help="Disable Text-to-Speech audio output.",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=config.DEFAULT_STT_LANG,
        help="Primary speech recognition language (e.g. en-IN, hi-IN).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging.",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # 1. Diagnostic Mode
    if args.doctor:
        success = print_doctor_report()
        sys.exit(0 if success else 1)

    # 2. List Microphones Mode
    if args.list_mics:
        devices = Listener.list_microphones()
        print("\nAvailable Audio Input Devices:")
        if not devices:
            print("  No audio input devices found.")
        else:
            for dev in devices:
                print(f"  [{dev['index']}] {dev['name']}")
        print()
        sys.exit(0)

    # 3. GUI Mode (Placeholder for Milestone 5)
    if args.gui:
        try:
            from gui.app import launch_gui

            launch_gui(dry_run=args.dry_run, mute=args.mute)
            sys.exit(0)
        except ImportError:
            print("\n[Notice] GUI module (PySide6) will be fully integrated in Milestone 5.")
            print("         Running interactive text mode for now...\n")
            args.text = True

    # 4. Voice vs Text Mode
    is_voice = args.voice and not args.text
    app = MarutiApp(
        voice_mode=is_voice,
        dry_run=args.dry_run,
        mute=args.mute,
        mic_index=args.mic,
        language=args.lang,
    )

    if is_voice:
        app.run_voice_loop()
    else:
        app.run_text_loop()


if __name__ == "__main__":
    main()
