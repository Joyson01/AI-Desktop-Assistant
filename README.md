# MARUTI: Linux Voice-Controlled Desktop-Assistant Starter

MARUTI is a Linux voice-controlled desktop-assistant starter built in Python. It provides hands-free and text-driven control over desktop applications, browser navigation, volume, text editing, and screen perception with deterministic rule-based intent parsing, safe execution boundaries, and human-in-the-loop confirmation gates.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   MARUTI Architecture                                  │
│                                                                                        │
│  [Microphone / Text]                                                                   │
│         │                                                                              │
│         ▼                                                                              │
│  [Speech-to-Text] ──────────► Google Web Speech API (en-IN / hi-IN)                    │
│         │                                                                              │
│         ▼                                                                              │
│  [Intent Router] ───────────► Rule-Based Regex & Fuzzy Normalizer (Local & Offline)    │
│         │                                                                              │
│         ▼                                                                              │
│  [Assistant Façade] ────────► AssistantStateMachine (Thread-Safe Lifecycle)            │
│         │                                                                              │
│         ▼                                                                              │
│  [Safety Policy Engine] ────► Deterministic Risk Tiering (SAFE / SENSITIVE / BLOCKED)  │
│         │                                                                              │
│         ▼                                                                              │
│  [Action Registry] ─────────► System Control (Allowlisted Apps & Folders)              │
│                                Desktop Input (Bounded Scroll & Typing via Clipboard)   │
│                                Audio Control (ALSA / PulseAudio / PipeWire Volume)     │
│                                Browser Controller (URL & YouTube Query Navigation)     │
│                                Screen Perception (pytesseract OCR & Visual Targeting)  │
│         │                                                                              │
│         ▼                                                                              │
│  [Feedback & Logging] ──────► Spoken TTS (spd-say / espeak-ng / pyttsx3)               │
│                                Redacted JSONL Audit Log (logs/actions.jsonl)           │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Setup and Run Instructions

### System Prerequisites (Linux)

- **OS**: Linux (tested on Ubuntu 24.04 LTS / GNOME on Wayland with XWayland).
- **Python**: Python 3.10+ (tested on Python 3.14.4).
- **Audio Input**: PortAudio development headers and microphone permissions:
  ```bash
  sudo apt install portaudio19-dev python3-pyaudio
  ```
- **Audio Output (TTS)**: Speech Dispatcher or eSpeak:
  ```bash
  sudo apt install speech-dispatcher espeak-ng
  ```
- **Screen Perception / OCR (Optional)**:
  ```bash
  sudo apt install tesseract-ocr
  ```
- **Window Management (Optional for X11 / XWayland)**:
  ```bash
  sudo apt install xdotool wmctrl xclip
  ```

### Installation

```bash
# 1. Clone repository and navigate to workspace
cd /home/joyson/Documents/Maruti

# 2. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Create local environment configuration
cp .env.example .env
```

### Running MARUTI

| Mode                          | Command                                                       | Description                                                                                                                |
| ----------------------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **GUI Mode**                  | `.venv/bin/python main.py --gui` or `python app.py --gui`     | PySide6 desktop interface with live status orb, transcript box, Stop button, mic toggle, and review-before-execution mode. |
| **Voice Mode**                | `.venv/bin/python main.py --voice` or `python app.py --voice` | Hands-free terminal loop with persistent microphone listener, ambient noise calibration, and speech prompts.               |
| **Interactive CLI (Default)** | `.venv/bin/python main.py --text` or `python app.py`          | Terminal text REPL for keyboard-driven command execution.                                                                  |
| **Dry-Run Simulation**        | `.venv/bin/python main.py --text --dry-run`                   | Safe simulation mode; logs and returns planned actions without executing subprocesses, mouse clicks, or volume changes.    |
| **System Diagnostics**        | `.venv/bin/python main.py --doctor`                           | Verifies runtime capabilities: audio devices, TTS engines, session type (Wayland/X11), and Tesseract OCR availability.     |
| **Test Suite**                | `.venv/bin/pytest -v`                                         | Executes complete automated test suite (173 passing tests).                                                                |

---

## 2. Configuration Settings (`.env`)

MARUTI reads environment variables from an optional `.env` file located in the project root via `config.py`. Every configuration setting has a safe built-in default:

| Setting                            | Type    | Safe Default       | Description                                                                                                                                                    |
| ---------------------------------- | ------- | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GEMINI_API_KEY`                   | String  | `""` (empty)       | Google AI Studio API key used strictly for general conversational questions (`chat` intent). When empty, MARUTI runs fully offline with its rule-based router. |
| `GEMINI_MODEL`                     | String  | `gemini-2.5-flash` | Gemini model name used for general chat fallback.                                                                                                              |
| `MARUTI_CITY`                      | String  | `Boisar`           | Default geographical city used for weather queries when no location is specified.                                                                              |
| `MARUTI_STT_LANG`                  | String  | `en-IN`            | Primary BCP-47 language locale for Google Web Speech recognition.                                                                                              |
| `MARUTI_STT_SECONDARY_LANG`        | String  | `hi-IN`            | Secondary fallback language locale tried if primary transcription detects no speech.                                                                           |
| `MARUTI_STT_ENERGY_THRESHOLD`      | Integer | `300`              | Minimum audio energy level required to trigger speech boundary detection.                                                                                      |
| `MARUTI_STT_DYNAMIC_ENERGY`        | Boolean | `true`             | Continuously adjusts energy threshold based on background noise.                                                                                               |
| `MARUTI_STT_PAUSE_THRESHOLD`       | Float   | `0.8`              | Seconds of non-speaking silence before an audio capture is finalized.                                                                                          |
| `MARUTI_STT_NON_SPEAKING_DURATION` | Float   | `0.5`              | Minimum seconds of audio retained on each side of a detected phrase.                                                                                           |
| `MARUTI_STT_TIMEOUT`               | Float   | `5.0`              | Maximum seconds to wait for speech to begin before timing out.                                                                                                 |
| `MARUTI_STT_PHRASE_LIMIT`          | Float   | `10.0`             | Maximum duration in seconds allowed for a single spoken phrase.                                                                                                |
| `MARUTI_REVIEW_MODE`               | Boolean | `false`            | Sets initial state of GUI "Review voice commands before executing" checkbox. When `true`, voice transcriptions wait for user review.                           |
| `TESSERACT_CMD`                    | String  | `""` (empty)       | Path to Tesseract executable. When empty, auto-detects `/usr/bin/tesseract` or searches `PATH`.                                                                |
| `MARUTI_TTS_ENGINE`                | String  | `auto`             | Text-to-speech engine choice: `auto`, `spd-say`, `espeak-ng`, or `pyttsx3`.                                                                                    |
| `MARUTI_TTS_RATE`                  | Integer | `175`              | Speech synthesizer playback speed in words per minute.                                                                                                         |
| `MARUTI_TTS_VOLUME`                | Float   | `1.0`              | Synthesizer audio volume (clamped between `0.0` and `1.0`).                                                                                                    |
| `MARUTI_ACT_THRESHOLD`             | Float   | `0.85`             | Decision confidence threshold: scores at or above this value execute immediately.                                                                              |
| `MARUTI_ASK_THRESHOLD`             | Float   | `0.60`             | Ambiguity threshold: scores between `0.60` and `0.85` prompt for user clarification.                                                                           |
| `MARUTI_MAX_STEPS`                 | Integer | `6`                | Upper limit on sequential steps in automated workflows.                                                                                                        |

---

## 3. What Each Command Does

The table below describes the actual behavior of commands supported in the codebase today.

### Execution Constraints & Flags

- **Typed Input**: Available in CLI text mode (`--text`) and GUI input field.
- **Voice Mode**: Available in voice loop (`--voice`) and GUI Listen button.
- **Dry-Run by Default**: **No**. All commands execute live by default unless the `--dry-run` flag is explicitly passed.
- **Desktop Automation Dependency**: Commands marked **Yes** require desktop automation libraries (`pyautogui`, `PySide6.QtGui.QClipboard`, or `subprocess`).
- **Wayland / Linux Limitations**: Commands that inject synthetic clicks or read window titles depend on XWayland or compositor permissions.

| Command Example                              | Routed Intent & Parameters                                        | Actual Runtime Behavior                                                                                                                  | Typed | Voice | Dry-Run Default? | Automation Dep.? | Wayland / Linux Limitations                                                                                                                                          |
| -------------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | :---: | :---: | :--------------: | :--------------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `open calculator`                            | `open` (`target="calculator"`)                                    | Spawns `gnome-calculator` (or `kcalc`/`galculator`) without shell injection.                                                             |  Yes  |  Yes  |        No        |       Yes        | Works under Wayland. Launch verified via binary search on `PATH`.                                                                                                    |
| `open browser`                               | `open` (`target="chrome"`)                                        | Spawns `google-chrome` (or `google-chrome-stable`/`chromium`).                                                                           |  Yes  |  Yes  |        No        |       Yes        | Works under Wayland.                                                                                                                                                 |
| `open firefox`                               | `open` (`target="firefox"`)                                       | Spawns `firefox` (or `firefox-esr`).                                                                                                     |  Yes  |  Yes  |        No        |       Yes        | Works under Wayland.                                                                                                                                                 |
| `open files`                                 | `open` (`target="file explorer"`)                                 | Spawns graphical file manager (`nautilus`, `thunar`, or `dolphin`).                                                                      |  Yes  |  Yes  |        No        |       Yes        | Works under Wayland.                                                                                                                                                 |
| `open text editor`                           | `open` (`target="notepad"`)                                       | Spawns `gnome-text-editor` (or `gedit`, `mousepad`, `kate`).                                                                             |  Yes  |  Yes  |        No        |       Yes        | Works under Wayland. Sets active editor context.                                                                                                                     |
| `open google.com`                            | `open` (`kind="site"`, `target="https://google.com"`)             | Validates URL scheme (`http`/`https` only) and launches in default browser via `webbrowser.open()`.                                      |  Yes  |  Yes  |        No        |       Yes        | Works under Wayland.                                                                                                                                                 |
| `search Python tutorials`                    | `web_search` (`query="Python tutorials"`)                         | Formats URL `https://www.google.com/search?q=Python+tutorials` and opens in default browser. Updates active context to Google.           |  Yes  |  Yes  |        No        |       Yes        | Works under Wayland.                                                                                                                                                 |
| `search youtube keyboard shortcuts`          | `youtube` (`query="keyboard shortcuts"`, `play=False`)            | Opens YouTube search results page for query `keyboard shortcuts`. Sets active browser context to YouTube.                                |  Yes  |  Yes  |        No        |       Yes        | Works under Wayland.                                                                                                                                                 |
| `play Saiyara song`                          | `youtube` (`query="Saiyara song"`, `play=True`)                   | Opens YouTube search results; triggers video play click if Tesseract OCR is available, otherwise requests manual video selection.        |  Yes  |  Yes  |        No        |       Yes        | Works under Wayland. Auto-click blocked without Tesseract.                                                                                                           |
| `type hello`                                 | `type_text` (`text="hello"`)                                      | Injects text `hello` at current cursor position via Qt clipboard paste simulation (`Ctrl+V`). Preserves unicode.                         |  Yes  |  Yes  |        No        |       Yes        | Target window must have keyboard focus. In pure Wayland, global focus switching is restricted.                                                                       |
| `type my password is secret123`              | `type_text` (`text="..."`)                                        | **Sensitive Gate**: Password/credential text triggers human confirmation before typing.                                                  |  Yes  |  Yes  |        No        |       Yes        | Mandates user confirmation.                                                                                                                                          |
| `scroll up 3`                                | `scroll` (`direction="up"`, `repetitions=3`, `amount=400`)        | Issues 3 upward scroll operations of 400 ticks each with 80ms intervals via PyAutoGUI.                                                   |  Yes  |  Yes  |        No        |       Yes        | Requires pointer to be over a scrollable window. On Wayland, pointer must be inside an XWayland surface or active window.                                            |
| `scroll down 3`                              | `scroll` (`direction="down"`, `repetitions=3`, `amount=400`)      | Issues 3 downward scroll operations of 400 ticks each via PyAutoGUI.                                                                     |  Yes  |  Yes  |        No        |       Yes        | Same as above. Repetitions are bounded to maximum 10.                                                                                                                |
| `scroll to top`                              | `scroll` (`direction="up"`, `amount=2000`, `boundary="top"`)      | Issues large bounded scroll up to reach top of page/document.                                                                            |  Yes  |  Yes  |        No        |       Yes        | Pointer over window required.                                                                                                                                        |
| `scroll to bottom`                           | `scroll` (`direction="down"`, `amount=2000`, `boundary="bottom"`) | Issues large bounded scroll down to reach end of page/document.                                                                          |  Yes  |  Yes  |        No        |       Yes        | Pointer over window required.                                                                                                                                        |
| `press enter` / `press tab` / `press escape` | `press_keys` (`keys=["enter"]` etc.)                              | Dispatches single key press to active window.                                                                                            |  Yes  |  Yes  |        No        |       Yes        | Target window must have active focus.                                                                                                                                |
| `press left arrow` / `press right arrow`     | `press_keys` (`keys=["left"]` etc.)                               | Dispatches arrow key navigation to active editor or document.                                                                            |  Yes  |  Yes  |        No        |       Yes        | Target window focus required.                                                                                                                                        |
| `press backspace` / `press delete`           | `press_keys` (`keys=["backspace"]` etc.)                          | Dispatches backspace or delete key stroke.                                                                                               |  Yes  |  Yes  |        No        |       Yes        | Target window focus required.                                                                                                                                        |
| `select all` / `copy` / `paste` / `cut`      | `press_keys` (`ctrl+a`, `ctrl+c`, etc.)                           | Dispatches standard editing shortcut to active application.                                                                              |  Yes  |  Yes  |        No        |       Yes        | Clipboard operations via Qt / XWayland.                                                                                                                              |
| `undo` / `redo`                              | `edit_undo` / `edit_redo`                                         | Dispatches undo (`Ctrl+Z`) or platform redo (`Ctrl+Shift+Z` on Linux, `Ctrl+Y` on Windows).                                              |  Yes  |  Yes  |        No        |       Yes        | Target window focus required.                                                                                                                                        |
| `start dictation` / `stop dictation`         | `start_dictation` / `stop_dictation`                              | Toggles literal dictation mode where spoken utterances are typed directly without command parsing.                                       |  Yes  |  Yes  |        No        |       Yes        | Context-aware state toggle.                                                                                                                                          |
| `run bash`                                   | `run_shell_command`                                               | **BLOCKED**: Arbitrary terminal command execution is strictly blocked by security policy.                                                |  Yes  |  Yes  |        No        |        No        | Blocked on all platforms.                                                                                                                                            |
| `click Sign in`                              | `click` (`label="Sign in"`)                                       | Takes screen capture, runs Tesseract OCR to find bounding box matching "Sign in", and dispatches mouse click to center coordinate.       |  Yes  |  Yes  |        No        |       Yes        | **Blocked if Tesseract is missing.** Fails on scaled displays (125%/150%) due to DPI coordinate offset. Wayland restricts global coordinate clicks outside XWayland. |
| `confirm`                                    | Handled by confirmation prompt                                    | Approves a pending sensitive action during an interactive `(yes/no)` prompt or modal. (Outside a prompt, routed to conversational chat). |  Yes  |  Yes  |        No        |        No        | No desktop automation dependency.                                                                                                                                    |
| `cancel`                                     | `cancel` / Emergency stop                                         | Immediately halts active TTS speech, aborts speech listening, cancels active action plan, and returns assistant to `IDLE`.               |  Yes  |  Yes  |        No        |        No        | Always available. Works in all modes.                                                                                                                                |
| `exit assistant`                             | `exit`                                                            | Speaks farewell message, flushes pending audit logs, and cleanly shuts down assistant process.                                           |  Yes  |  Yes  |        No        |        No        | Always available.                                                                                                                                                    |
| `kholo calculator`                           | `open` (`target="calculator"`)                                    | Hinglish verb mapping translates `kholo` -> `open`. Launches `gnome-calculator`.                                                         |  Yes  |  Yes  |        No        |       Yes        | Works under Wayland.                                                                                                                                                 |
| `dhoondo scholarship information`            | `web_search` (`query="scholarship information"`)                  | Hinglish verb mapping translates `dhoondo` -> `search`. Dispatches Google search for exact query payload.                                |  Yes  |  Yes  |        No        |       Yes        | Works under Wayland.                                                                                                                                                 |
| `likho namaste`                              | `type_text` (`text="namaste"`)                                    | Hinglish verb mapping translates `likho` -> `type`. Types "namaste" via clipboard injection.                                             |  Yes  |  Yes  |        No        |       Yes        | Focus required. Unicode text supported via Qt clipboard.                                                                                                             |

---

## 4. GUI Listen & Voice Command Flow

In GUI mode (`.venv/bin/python main.py --gui`), voice commands follow a deliberate safety workflow:

1. **Audio Capture**: Clicking **"Mic: OFF"** (or triggering voice listening) spawns a background `VoiceWorker` thread that listens through the persistent `Listener` device.
2. **Speech Transcription**: Captured audio is converted to text via Google Web Speech. The recognized phrase is displayed in the GUI transcript log as `Heard: <phrase>`.
3. **Review Mode Behavior**:
   - The GUI features a **"Review voice commands before executing"** checkbox (controlled by `MARUTI_REVIEW_MODE` in `.env`).
   - **When Review Mode is checked**: The transcribed phrase is automatically inserted into the text input box. MARUTI logs: `Command held for review. Edit above and press Send or Enter to execute.` **The command does not execute automatically.** The user must review, edit any transcription errors, and click **Send** (or press `Enter`).
   - **When Review Mode is unchecked**: The recognized phrase is submitted directly to the execution pipeline without manual review.
4. **Immediate Stop Button**: The red **"Stop"** button connects directly to `Assistant.cancel()`, instantly stopping speech synthesis, voice capture, and queued tasks.

---

## 5. Application Allowlist & Subprocess Safety

MARUTI strictly rejects arbitrary shell execution:

- **Registry Allowlist (`registry.py`)**: Only predefined desktop applications and known directories can be launched:
  - `chrome` (`google-chrome`, `chromium-browser`, `chromium`)
  - `firefox` (`firefox`, `firefox-esr`)
  - `edge` (`microsoft-edge`)
  - `notepad` / `text editor` (`gnome-text-editor`, `gedit`, `mousepad`, `kate`, `code`)
  - `calculator` (`gnome-calculator`, `kcalc`, `galculator`)
  - `paint` (`pinta`, `gimp`, `krita`)
  - `file explorer` / `files` (`nautilus`, `thunar`, `nemo`, `dolphin`, `pcmanfm`)
  - `vs code` (`code`, `code-oss`, `codium`)
  - `word` / `excel` / `powerpoint` (`libreoffice`)
  - `settings` (`gnome-control-center`, `unity-control-center`, `xfce4-settings-manager`)
  - `task manager` (`gnome-system-monitor`, `ksysguard`)
  - `calendar` (`gnome-calendar`)
  - `clocks` (`gnome-clocks`)
  - `disks` (`gnome-disks`)
- **Unknown Applications**: Any application not in the registry is rejected with confidence `< 0.6` and routed to `unknown`.
- **No Arbitrary Shell Injection**: Application execution uses direct binary lists (`[binary_path, arg1, ...]`) via `subprocess.Popen` with `shell=False`. Terminal wrappers (`bash`, `sh`, `gnome-terminal`) are blocked from executing arbitrary user strings.
- **URL Protocol Restraints**: The system controller strictly validates URLs, permitting only `http://` and `https://`. Protocol schemes like `file://`, `javascript:`, and `data:` are rejected.

---

## 6. Safety Confirmation Engine (`confirm` & `cancel`)

To prevent accidental data loss, financial charges, or system instability, MARUTI enforces safety policies via `core/policy.py`:

### Risk Classification

- **SAFE**: Read-only or benign actions (opening allowlisted apps, web search, volume adjustment, scrolling, typing) execute without prompting.
- **SENSITIVE**: Consequential or destructive actions require explicit user confirmation before any operating system action is taken.
- **BLOCKED**: Actions that violate security rules (arbitrary shell commands) or require unavailable platform capabilities (OCR when Tesseract is missing).

### What Triggers Confirmation

1. **Sensitive Intents**:
   - `close_window` (closing active desktop application windows)
   - `delete_file` / `overwrite_file` (modifying filesystem files)
   - `save_file_as` when destination file already exists
   - `change_security_settings`
   - `browser_login` / `browser_payment`
2. **Destructive Regex Patterns**:
   - Any argument containing commands like `rm -rf`, `mkfs`, `format`, or `drop table`.
3. **Sensitive OCR Clicks**:
   - Any click target whose label contains `pay`, `buy`, `purchase`, `delete`, `checkout`, or `transfer`.

### What `confirm` and `cancel` Do

- **When Awaiting Confirmation**:
  - The assistant enters `AWAITING_CONFIRMATION` state and displays/speaks a confirmation question (e.g., `"Do you want me to close the current window?"`).
  - **Confirming**: Spoken or typed `confirm`, `yes`, `haan`, `sure`, or `ok` (or clicking "Yes" in the GUI modal) authorizes the action and proceeds with execution.
  - **Cancelling**: Spoken or typed `cancel`, `no`, `nahi`, or empty input aborts the action. The assistant replies: `"Action cancelled by user."`
- **Standalone `cancel` Command**:
  - Spoken or typed at any time, `cancel` halts speech synthesis immediately (`speaker.stop()`), resets the assistant state machine to `IDLE`, and drops pending tasks.

---

## 7. OCR Screen Perception & Visual Click Limitations

Commands like `click Sign in`, `read the screen`, and `what is on my screen` rely on `core/perception.py` and `pytesseract`:

### Limitations & Known Failure Modes

1. **Missing Tesseract Binary**:
   - If `tesseract-ocr` is not installed on the system PATH, the assistant capability check classifies the action as `BLOCKED`. Execution safely fails with:
     `"Capability blocked: Tesseract OCR is not installed."`
2. **Linux Wayland Restrictions**:
   - Pure Wayland compositors prohibit applications from capturing global desktop screenshots or reading other windows' pixel buffers. Screen capture falls back to XWayland compatibility layers or requires active user portal grants.
3. **Display Scaling (HiDPI / Fractional Scaling)**:
   - When display scaling is enabled (e.g. 125%, 150%, or 200%), the pixel dimensions of the captured screenshot buffer differ from PyAutoGUI's virtual coordinate grid. This offset can cause mouse clicks to land outside the intended button.
4. **Font and Contrast Variance**:
   - Small, low-contrast, or stylized web fonts frequently fail OCR character recognition, resulting in:
     `"Could not find any element matching '<label>' on the screen."`

---

## 8. Privacy & Security Architecture

1. **Speech Recognition**:
   - Voice transcription uses Google Web Speech API (`speech_recognition.Recognizer.recognize_google`).
   - Audio is buffered entirely in memory during phrase capture and transmitted securely over TLS.
   - **No raw voice recordings are stored or saved to disk.**
2. **Cloud AI / LLM Usage**:
   - **Local Commands Stay Local**: App launching, web searches, volume control, scrolling, text typing, and window switching are processed 100% locally by deterministic regex rules. No command text for desktop automation is sent to an LLM.
   - **Conversational Chat Only**: Google Gemini (via `GEMINI_API_KEY` in `brain.py`) or OpenAI (if configured) is only invoked for conversational questions (`chat` intent) when an API key is provided. If no key is set, MARUTI runs fully offline.
3. **Audit Log Credential Redaction**:
   - All executed actions are recorded in `logs/actions.jsonl`.
   - The logging engine (`core/action_logger.py`) automatically sanitizes transcripts and arguments before writing to disk, redacting passwords, authentication tokens, OTPs, PINs, and payment card numbers.

---

## 9. Troubleshooting

### 1. Microphone Not Detected

- Run `.venv/bin/python main.py --doctor` to inspect detected input devices.
- Verify PipeWire / PulseAudio microphone volume and mute status:
  ```bash
  pactl list sources short
  pactl set-source-mute @DEFAULT_SOURCE@ 0
  ```
- Specify hardware device index in CLI if default index fails:
  ```bash
  .venv/bin/python main.py --voice --mic-index 1
  ```

### 2. PyAudio Installation Failure on Python 3.14

- Ensure system headers are present before installing:
  ```bash
  sudo apt install portaudio19-dev libasound2-dev
  pip install --upgrade pyaudio
  ```

### 3. Google Speech Recognition Timeouts or Network Errors

- Ensure active internet connectivity (Google Web Speech requires internet access).
- Increase phrase capture timeout in `.env`:
  ```ini
  MARUTI_STT_TIMEOUT=8.0
  MARUTI_STT_PHRASE_LIMIT=12.0
  ```
- Adjust `MARUTI_STT_ENERGY_THRESHOLD=400` if ambient room noise triggers false listening states.

### 4. Text-To-Speech (TTS) Has No Sound

- Test speech dispatcher from terminal:
  ```bash
  spd-say "testing maruti speech"
  ```
- If speech dispatcher is silent, switch to `espeak-ng` or `pyttsx3` in `.env`:
  ```ini
  MARUTI_TTS_ENGINE=espeak-ng
  ```

### 5. Desktop Automation Disabled or No Mouse/Keyboard Effect

- If running with `--dry-run`, desktop automation side effects are intentionally bypassed. Remove `--dry-run` to execute actions.
- Under Wayland, ensure target application windows run under XWayland or possess active keyboard focus before typing.

### 6. Missing Desktop Application Executables

- If MARUTI reports `Application 'calculator' is not installed on this system`:
  ```bash
  sudo apt install gnome-calculator gnome-text-editor nautilus
  ```

### 7. Tesseract OCR Missing or Failing

- Install Tesseract and language packages:
  ```bash
  sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin
  ```
- Verify binary path: `which tesseract` (typically `/usr/bin/tesseract`). Set `TESSERACT_CMD=/usr/bin/tesseract` in `.env`.

---

## 10. Not Implemented Yet

The following capabilities are planned for future milestones but are **not implemented in the codebase today**:

- **Offline Local Wake-Word Engine**: Continuous background wake-word detection (e.g., Porcupine or openWakeWord) is not implemented; current voice mode listens sequentially after prompt calibration.
- **Native Wayland Portal Input**: Direct injection of mouse and keyboard events via `libei` / `xdg-desktop-portal` without XWayland.
- **Multi-Monitor DPI Auto-Compensation**: Automatic coordinate scaling compensation across multi-monitor setups with mixed DPI scaling.
- **Direct Browser DOM / CDP Driver**: Direct element targeting via Chrome DevTools Protocol or accessibility trees (current visual targeting uses OCR).
- **Offline Speech-to-Text**: Local on-device STT models (Whisper.cpp or Vosk) for air-gapped speech recognition.
- **Autonomous Vision-Language Agent**: Multi-turn visual reflection loops where an agent self-corrects based on post-action screen diffs.
