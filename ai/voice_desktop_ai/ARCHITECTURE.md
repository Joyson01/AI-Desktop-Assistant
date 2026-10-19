# Maruti Architecture Map

This map records the current system before incremental upgrades. Existing modules remain available.

## Current live path

`assistant.py` is the runtime entry point. Its flow is:

1. `voice/stt.py` listens and transcribes speech.
2. `voice/speech_normalizer.py` normalizes Hindi/Hinglish aliases.
3. `brain/intent.py` parses one command into an intent.
4. `brain/planner.py` currently wraps that intent in a one-step plan.
5. `perception/observer.py` combines UI Automation state with optional OCR fallback.
6. `perception/uia.py` and `uia_engine.py` resolve and perform UIA/OCR-backed targets.
7. `actions/engine.py` executes the existing intent actions and verifies state.
8. `verification/verifier.py` provides the current lightweight verification boundary.
9. `tts.py` speaks responses.

The assistant preserves short-term context, supports dry-run mode, retries failed actions, and keeps the wake-word/type-mode behavior in the existing runtime.

## Working components to preserve

- Speech recognition and Hindi/Hinglish normalization in `voice/` and `speech.py`.
- Text-to-speech in `tts.py`.
- PyAutoGUI mouse/keyboard behavior in `actions/engine.py` and the existing test scripts.
- Windows UI Automation and OCR fallback in `perception/`, `uia_engine.py`, and `vision_engine.py`.
- Existing intent parsing, conversation handling, scrolling, typing, and verification tests.

## Overlap and conflicts

- `assistant.py` uses `brain/llm.py`, whose current screen analysis only returns UI/OCR candidate text.
- `brain/gemini_client.py` is an optional SDK boundary and is covered by a graceful no-key test, but it is not connected to the live assistant.
- `computer/action_executor.py` is a separate structured-action executor. It validates coordinates and supported action names, but the live assistant currently uses `actions/engine.py` instead.
- `computer/actions.py` is the isolated provider-independent action protocol. It validates model-shaped actions and adapts them to `computer/action_executor.py`; it is not connected to the live assistant.
- `brain/visual_brain.py` defines the provider-independent visual brain contract and a deterministic mock. It accepts the screenshot plus optional context/history and returns validated `Action` data only; it has no computer-control operations.
- `brain/screen_context.py` defines immutable `ScreenContext` and `BrainInput` observations. They carry the screenshot, dimensions, active app/window, optional URL/OCR/UIA metadata, goal, action history, task step, and verification context.
- `brain/task_orchestrator.py` provides a bounded, isolated multi-step loop. It observes, asks the provider-independent brain for one action, executes through `ActionPipeline`, observes again, verifies, and then re-analyzes. Its `TaskState` preserves action and screenshot references, status, retries, and step limits.
- `verification/verifier.py` preserves the legacy boolean helpers and now also provides provider-neutral `VerificationResult` and `RuleBasedVerifier` transition checks. Verification is observation-only and can compare expected state with the new screen without OCR.
- `brain/providers/grok_visual_brain.py` is an optional xAI adapter implementing the provider-independent `BrainInput` -> `VisualBrainResult` contract. It sends one screenshot and one next-action request through the OpenAI-compatible xAI endpoint, but never executes actions.
- `brain/providers/provider_config.py` reads `XAI_API_KEY` and `XAI_MODEL` without network access and exposes only a secret-free status.
- `scripts/smoke_grok_visual_brain.py` is a manual, non-executing smoke test. It requires `RUN_REAL_GROK_SMOKE=1` for one real request; `--dry-run` prepares a screenshot and makes no request.
- `assistant.py` now has an additive `MARUTI_GROK_LIVE` gate. Only `MARUTI_GROK_LIVE=1` plus a configured xAI key enables the isolated `TaskOrchestrator`; otherwise the existing intent/planner/OCR/UIA path remains active. The live callback currently confirms that a new valid observation exists, not that a provider-specific semantic state was reached.
- The live Grok verifier now returns `VerificationResult("uncertain")` when an action has no expected semantic state. A fresh screenshot is observation health only and cannot independently produce task success; expected states are compared by the provider-neutral `RuleBasedVerifier`.
- `action_engine.py`, `intent.py`, and the standalone `*_test.py` scripts are older parallel surfaces. They remain available and are not the runtime authority identified above.
- `voice_command.py`, `voice_search.py`, and several root test scripts execute work at import/run time; treat them as manual legacy tools rather than libraries.

## Intended upgrade boundary

Keep the current live path as the fallback while introducing structured computer actions behind explicit interfaces:

- Planner: expand natural-language intents into logical steps.
- Visual brain: optionally analyze a screenshot and return validated structured actions.
- Executor: reuse controlled PyAutoGUI/UIA operations; never run arbitrary code.
- Verifier: observe a new screen and determine whether the expected state changed.
- Router: choose computer, web, knowledge, or conversation handling before computer-use reasoning.

The first structured-action upgrade is isolated behind tests and an explicit adapter, rather than rewriting `assistant.py` or deleting the current OCR/UIA path.

## Future multimodal action loop

```text
VOICE
	-> STT
	-> USER GOAL
	-> VISUAL BRAIN
	-> STRUCTURED ACTION
	-> ACTION VALIDATOR
	-> STRUCTURED ACTION ADAPTER
	-> ACTION EXECUTOR
	-> SCREENSHOT
	-> VERIFICATION
	-> NEXT ACTION
```

The screenshot is the primary future input for multimodal visual reasoning.
OCR remains optional fallback/helper perception metadata and is not required by
the visual brain contract.

The isolated multi-step loop is:

```text
VOICE
	-> STT
	-> USER GOAL
	-> TASK ORCHESTRATOR
	-> SCREENSHOT
	-> VISUAL BRAIN
	-> ONE STRUCTURED ACTION
	-> ACTION VALIDATOR
	-> ACTION PIPELINE
	-> ACTION EXECUTOR
	-> SCREENSHOT
	-> VERIFICATION
	-> TASK ORCHESTRATOR
	-> NEXT ACTION
```

This loop is currently tested with `MockVisualBrain` and fake executors. It is
not connected to `assistant.py` or Gemini.

## Real Visual Brain Provider Layer

`VisualBrain` remains provider-independent. The optional `GrokVisualBrain`
adapter receives `BrainInput`, sends the screenshot as a multimodal image data
URL, requests one strict JSON-schema decision, and converts the response into
the existing `VisualBrainResult` and `Action` types. Invalid JSON, unsupported
actions, low-confidence clicks, ambiguity, missing targets, and provider
errors become safe `ask_user` results.

The provider has no mouse, keyboard, shell, subprocess, or executor access.
`ActionPipeline` remains responsible for validation and controlled execution;
verification remains outside the provider. Credentials use `XAI_API_KEY` and
model selection uses `XAI_MODEL`; neither is stored in source.

## Real Grok Brain Validation

`scripts/validate_grok_brain.py` provides explicit scenario validation for
`open_chrome`, `enter_button`, `reload`, `search_saiyaara`, and
`account_search_play`. Each invocation captures one screen, sends one
`BrainInput`, validates one `VisualBrainResult`, and prints only safe metadata.
It requires both `--real` and `RUN_REAL_GROK_SMOKE=1`; without them it makes no
request. It never imports or calls `ActionExecutor`, `ActionPipeline`,
PyAutoGUI, or UIA, so returned actions cannot affect the computer.

When live mode is explicitly enabled, `assistant.py` routes a command through
the existing `TaskOrchestrator`, `ActionPipeline`, and `ActionExecutor` one
validated action at a time. A missing provider, invalid response, provider
error, or failed task returns control to the legacy path; model ambiguity is
reported to the user without executing an action. The default remains off.
Semantic post-action verification for arbitrary live desktop goals remains a
blocker: the current callback verifies observation availability only, while
the deterministic `RuleBasedVerifier` requires an expected state. Provider
results can now carry `expected_state`; without that evidence the live route
fails safely through uncertainty/retry rather than claiming success.

Future provider layout:

```text
brain/providers/
	grok_visual_brain.py
	gemini_visual_brain.py   # future
	openai_visual_brain.py    # future
```

The adapter is tested with a fake transport and fake executor. It is not
connected to the live assistant and does not run automatically.

## Visual Grounding Diagnostics

The provider request uses a real system-role instruction plus a separate user
multimodal message. The user message contains the goal/context JSON and one PNG
`input_image` data URL. The strict schema lists the complete action shape and
requires its fields, while `ActionValidator` remains the final authority.

The diagnostic mode reports only screenshot dimensions, image MIME type, image
byte length, image presence, model, returned action, confidence, and validation
status. The earlier real validations exposed no raw provider response, so the
exact reason for each `ask_user` result cannot be recovered retrospectively;
they may have been genuine visual ambiguity or an adapter/provider failure,
both of which were intentionally collapsed to safe `ask_user` results. The
new request shape makes the visual instruction explicit and observable without
logging secrets or screenshots.

Deterministic grounding fixtures cover visible Chrome and Enter targets, a
search box, keyboard shortcuts, missing and ambiguous targets, invalid
coordinates, and one-next-action behavior with empty OCR/UIA metadata. They
prove the transport and validation contract only; they do not claim that a
real model can identify arbitrary desktop targets. The next real visual test
should therefore use one clearly visible, low-risk target and retain execution
disabled.

## Manual Grok Smoke Validation

The smoke path is explicitly separate from execution:

```text
Screen capture
	-> BrainInput
	-> GrokVisualBrain
	-> VisualBrainResult
	-> validation result only
```

The smoke script never invokes `ActionExecutor`, `ActionPipeline`, PyAutoGUI,
or UIA. Automated tests use fake transport, screenshots, and executors. A
real request is possible only when `RUN_REAL_GROK_SMOKE=1` is explicitly set;
without that flag the script exits safely. `--dry-run` never calls Grok.
API credentials are environment-only and are never printed or stored in source.
`assistant.py` is not invoked by this manual smoke path, and the existing
fallback path remains active.

Execution success is not task success. A mouse click or key press can execute
successfully while the requested screen transition fails or remains uncertain.
The new screen must be observed and verified before the orchestrator proceeds.

Each brain call receives a `BrainInput` containing:

```text
goal
screen: screenshot, dimensions, active app/window, optional URL/OCR/UIA data
action history
last action
last verification
task step
optional conversation context
```

Screenshot is the primary observation. OCR is optional helper/fallback data,
and UIA is optional structured metadata. `VisualBrain` is provider-independent;
Gemini remains a future provider and is not connected.

## Simulated Workflow Harness

The deterministic fixtures in `tests/fixtures/` exercise realistic screen
transitions before any provider is connected. `FakeObserver` returns the next
immutable `ScreenContext`, `WorkflowBrain` selects one result from the current
screen state, and `FakeExecutor` records validated payloads without touching
the computer.

A multi-step command is represented as repeated observe -> think -> act ->
verify transitions. Verification failures return to the brain with the new
screen and failure result, subject to the orchestrator retry and step limits.
Ambiguous or missing targets return `ask_user` and stop safely. These tests do
not connect to the live assistant, Gemini, or real mouse and keyboard control.

The isolated action pipeline is:

```text
VisualBrain
  -> VisualBrainResult
  -> Action
  -> ActionValidator
  -> StructuredActionAdapter
  -> Existing ActionExecutor
```

After execution, the orchestrator observes and verifies:

```text
OBSERVE NEW SCREEN
	-> Verification
	-> VerificationResult
	-> BrainInput
	-> NEXT ACTION
```

Gemini is still not connected, and the live assistant continues to use its
existing action path.

## Environment findings

- The existing `.venv` runs the test suite: 13 tests passed at inspection time.
- The system Python can import `google.genai`; the repository `.venv` currently cannot.
- No `GEMINI_API_KEY` was present in the inspected process environment.
- Gemini must remain optional until the dependency and configuration are deliberately verified in the runtime interpreter.

## Provider Request Debugging

`GrokVisualBrain.debug_request()` and the validation script's `--debug` mode
expose a redacted request contract only: endpoint, model, message roles,
content types, PNG MIME/byte length, prompt text, strict response schema, and
settings. They never call the provider transport and never expose credentials,
image bytes, data URLs, or raw responses.

The provider request is structurally correct according to the current xAI
documentation: the Responses API receives a system message, a user message
containing `input_text` and `input_image`, and strict JSON Schema under
`text.format`. The remaining real-world grounding failure is therefore a
model/provider capability or interpretation issue, not request construction.
