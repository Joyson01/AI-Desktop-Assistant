import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brain.providers.grok_visual_brain import GrokVisualBrain
from brain.providers.provider_config import load_provider_config
from brain.screen_context import BrainInput, ScreenContext
from computer.actions import ActionValidator
from computer.screenshot import capture_screen


SCENARIOS = {
    "open_chrome": "Open Chrome",
    "enter_button": "Click on the Enter button",
    "reload": "Press Ctrl+R",
    "search_saiyaara": "Open Chrome, search YouTube and search Saiyaara",
    "account_search_play": "Open Chrome, click on Nehru Yadav account, search YouTube and play Saiyaara",
}


def main(argv=None, capture=capture_screen, brain_factory=GrokVisualBrain, environ=None):
    parser = argparse.ArgumentParser(description="Non-executing Grok visual-brain scenario validation.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--real", action="store_true", help="Make one real provider request; never execute its action.")
    parser.add_argument("--diagnostic", action="store_true", help="Print safe image/request metadata after validation.")
    parser.add_argument("--debug", action="store_true", help="Print a redacted request contract without calling Grok.")
    args = parser.parse_args(argv)
    config = load_provider_config(environ)

    if args.debug:
        try:
            screenshot = capture()
            brain_input = BrainInput(goal=SCENARIOS[args.scenario], screen=ScreenContext(screenshot=screenshot))
            brain = brain_factory(api_key="", model=config.model, transport=object())
            for key, value in brain.debug_request(brain_input).items():
                print(f"debug_{key}={value}")
        except Exception as error:
            print(f"debug_failed error={type(error).__name__}")
        return 0

    if not args.real:
        print("Real Grok validation is disabled. Re-run with --real for one request.")
        return 0
    if environ is not None and str(environ.get("RUN_REAL_GROK_SMOKE", "0")).strip() != "1":
        print("Real Grok validation is disabled. Set RUN_REAL_GROK_SMOKE=1 to opt in.")
        return 0
    if environ is None and __import__("os").environ.get("RUN_REAL_GROK_SMOKE", "0").strip() != "1":
        print("Real Grok validation is disabled. Set RUN_REAL_GROK_SMOKE=1 to opt in.")
        return 0
    if not config.configured:
        print("XAI_API_KEY is not configured; no request was made.")
        return 0

    try:
        screenshot = capture()
        screen = ScreenContext(screenshot=screenshot)
        brain_input = BrainInput(
            goal=SCENARIOS[args.scenario],
            screen=screen,
            context={"scenario": args.scenario},
        )
        brain = brain_factory(api_key=config.api_key, model=config.model)
        result = brain.analyze(brain_input)
        valid, _ = ActionValidator.validate(
            result.action.to_dict(),
            screen.screenshot.size if hasattr(screen.screenshot, "size") else None,
        )
        print(f"provider=xAI model={config.model} scenario={args.scenario}")
        print(f"result_type=VisualBrainResult action_type={result.action.name} confidence={result.confidence:.2f}")
        print(f"validation={'passed' if valid else 'failed'} action_executed=no")
        if args.diagnostic and hasattr(brain, "diagnostics"):
            for key, value in brain.diagnostics(brain_input, result).items():
                print(f"diagnostic_{key}={value}")
    except Exception as error:
        print(f"provider=xAI model={config.model} scenario={args.scenario} result=failed error={type(error).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())