import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brain.providers.grok_visual_brain import GrokVisualBrain
from brain.providers.provider_config import load_provider_config
from brain.screen_context import BrainInput, ScreenContext
from computer.screenshot import capture_screen


def main(argv=None, capture=capture_screen, brain_factory=GrokVisualBrain, environ=None):
    parser = argparse.ArgumentParser(description="Explicit, non-executing Grok visual-brain smoke test.")
    parser.add_argument("--dry-run", action="store_true", help="Prepare one screenshot but do not call Grok.")
    args = parser.parse_args(argv)
    config = load_provider_config(environ)

    if args.dry_run:
        print(f"provider=xAI model={config.model} configured={config.configured}")
        try:
            screenshot = capture()
            print(f"dry-run: screenshot prepared size={getattr(screenshot, 'size', 'unknown')}")
        except Exception as error:
            print(f"dry-run: screenshot unavailable ({type(error).__name__})")
        print("dry-run: no Grok request and no action execution")
        return 0

    if environ is None and not _real_smoke_enabled():
        print("Real Grok smoke test is disabled. Set RUN_REAL_GROK_SMOKE=1 to opt in.")
        return 0
    if environ is not None and str(environ.get("RUN_REAL_GROK_SMOKE", "0")).strip() != "1":
        print("Real Grok smoke test is disabled. Set RUN_REAL_GROK_SMOKE=1 to opt in.")
        return 0
    if not config.configured:
        print("XAI_API_KEY is not configured; no Grok request was made.")
        return 0

    try:
        screenshot = capture()
        screen = ScreenContext(screenshot=screenshot)
        brain_input = BrainInput(goal="Describe the next safe computer action.", screen=screen)
        result = brain_factory(api_key=config.api_key, model=config.model).analyze(brain_input)
        print(f"provider=xAI model={config.model} request=succeeded")
        print(f"returned_action={result.action.name} validation=passed confidence={result.confidence:.2f}")
    except Exception as error:
        print(f"provider=xAI model={config.model} request=failed error={type(error).__name__}")
    return 0


def _real_smoke_enabled():
    return __import__("os").environ.get("RUN_REAL_GROK_SMOKE", "0").strip() == "1"


if __name__ == "__main__":
    raise SystemExit(main())