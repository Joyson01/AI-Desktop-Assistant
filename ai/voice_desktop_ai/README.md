# MARUTI: AI Powered Voice Controlled Desktop Assistant

**MARUTI** is an intelligent, bilingual (English & Hindi/Hinglish) voice-controlled desktop assistant built with Python, PySide6, Google Generative AI (Gemini), and local desktop automation.

Developed as a Computer Engineering Capstone Project at **St. John College of Engineering and Management (SJCEM), Palghar**.

---

## Key Features

- **Modern PySide6 Desktop GUI**: Sleek dark interface with animated multi-state status orb, live conversation transcript bubbles, suggestion chips, and responsive layout.
- **Bilingual Voice & Text Control**: Full support for English, Hindi, and Hinglish phrasing (e.g., *"YouTube kholo"*, *"Maruti Chrome open karo"*, *"who is the owner of tesla"*).
- **Fast Local & Web Routing**:
  - `fast_local`: Instant keyboard shortcuts, window controls, and volume adjustments.
  - `web_media`: Intelligent YouTube search and direct URL resolution.
  - `web_navigation`: Official website resolution with caching.
  - `computer_visual`: Application launching (`google-chrome`, `nautilus`, `gedit`, `code`, `gnome-calculator`, etc.) and UI interactions.
  - `conversation`: Rule-based greetings or generative conversational AI via Gemini.
- **Safety Confirmations**: Critical actions like system shutdown or closing active windows require explicit user confirmation (via GUI dialog or voice/text affirmation).
- **Graceful Fallbacks**: Works out of the box even without a microphone (auto-switches to interactive text mode) or without Gemini API keys (reports unconfigured status and continues offline rule-based execution).

---

## Assistant States

The status orb and indicator dynamically signal the assistant's real-time state:

| State | Orb Indicator | Description |
| :--- | :--- | :--- |
| **Idle** | Slate Gray (Steady) | Waiting for user command or voice prompt |
| **Listening** | Emerald Green (Pulsing) | Microphone active, capturing user audio |
| **Thinking** | Sky Blue (Pulsing) | Intent routing and conversational AI processing |
| **Executing** | Amber (Steady) | Launching desktop application, URL, or action |
| **Speaking** | Violet (Pulsing) | Delivering text-to-speech voice response |
| **Error** | Coral Red (Steady) | Reporting diagnostic failure or missing resource |

---

## Installation & Setup

### 1. Prerequisites (Linux / Ubuntu / Debian)

```bash
# System libraries for audio, speech synthesis, and clipboard
sudo apt update
sudo apt install -y python3-dev python3-venv portaudio19-dev spd-say xclip libxcb-cursor0
```

### 2. Virtual Environment & Dependencies

```bash
cd ai/voice_desktop_ai

# Create virtual environment if not present
python3 -m venv .venv-linux

# Activate and install dependencies
source .venv-linux/bin/activate
pip install -r requirements.txt
```

### 3. Environment Configuration (`.env`)

Copy the example configuration:

```bash
cp .env.example .env
```

Add your optional API key (never commit `.env`):

```text
GEMINI_API_KEY=your-gemini-api-key-here
```

*(Note: MARUTI runs fully locally for desktop automation, navigation, and rule-based tasks even without an API key).*

---

## Launching MARUTI

### Launch the PySide6 Desktop GUI (Recommended)

```bash
./run.sh
# or
python assistant.py --gui
```

### Launch Interactive Terminal Text Mode

```bash
./run.sh --text
# or
python assistant.py --text
```

### Launch Headless Voice Listening Mode

```bash
./run.sh --voice
```

### Safe Dry-Run Mode (Mock Desktop Actions)

```bash
python assistant.py --gui --dry-run
```

---

## Running Automated Tests

All 339 unit and integration tests run headlessly without requiring an X11/Wayland display:

```bash
# Run complete test suite (339 tests)
QT_QPA_PLATFORM=offscreen ./.venv-linux/bin/pytest tests -q

# Run GUI specific tests
QT_QPA_PLATFORM=offscreen ./.venv-linux/bin/pytest tests/test_gui.py -v

# Run standalone routing verification scripts
./.venv-linux/bin/python test_smart_brain_verification.py
./.venv-linux/bin/python verify_web_resolver.py
```

---

## Supported Commands

| Category | Example Phrasing |
| :--- | :--- |
| **Greetings** | `maruti hello`, `hello maruti`, `namaste maruti`, `kaisa hai` |
| **Conversational AI** | `who is the owner of tesla`, `what is gravity`, `tell me a joke` |
| **Media & YouTube** | `YouTube kholo`, `YouTube pe Saiyaara search karo`, `play lofi music` |
| **Web Navigation** | `open google.com`, `open wikipedia`, `amazon open karo` |
| **Application Launch** | `open chrome`, `open calculator`, `open vs code`, `files kholo` |
| **Window & Desktop** | `scroll down`, `scroll up`, `copy`, `paste`, `select all` |
| **Safety Actions** | `shutdown` (prompts confirmation), `close window` (prompts confirmation) |

---

## Capstone Demonstration Workflow

To demonstrate MARUTI during evaluation or presentation:

1. **Launch GUI**:
   Run `./run.sh`. The modern dark window opens with the status orb in `Idle` (Slate Gray) and a welcome greeting appears in the transcript.
2. **Interactive Greeting**:
   Click the `Maruti Hello` suggestion chip or type `maruti hello`. The orb pulses in `Thinking` (Cyan) and switches to `Speaking` (Violet) as MARUTI responds: *"Hello! How can I help you today?"*.
3. **Bilingual Media Command**:
   Click `YouTube Kholo` or type `youtube pe lo-fi chill search karo`. MARUTI resolves the query and launches YouTube in the browser.
4. **Desktop Application Launch**:
   Type `open calculator` or `open chrome`. MARUTI identifies the Linux desktop binary and launches the application.
5. **Safety Confirmation**:
   Type `shutdown`. Instead of abruptly shutting down, MARUTI triggers a safety confirmation modal dialog and asks: *"Are you sure you want to shut down the computer?"*. Click **Cancel** to safely abort.
6. **Voice Mode Toggle**:
   Click the microphone button `🎙` in the dock. If a microphone is available, continuous listening activates with a glowing green orb. If unavailable, an inline diagnostic notification appears gracefully without crashing.

---

## Experimental Features & Current Limitations

- **Computer Vision & OCR Target Resolution (`perception/uia.py`, `perception/observer.py`)**: UI tree inspection and Tesseract OCR fallback are functional for coordinate clicking, but complex multi-step screen navigation remains experimental on Linux Wayland environments.
- **Live Grok Visual Orchestration (`brain/providers/grok_visual_brain.py`)**: Available as an optional experimental live provider when configured with `MARUTI_GROK_LIVE=1` and `XAI_API_KEY`.
- **System Audio Input on Wayland**: PyAudio requires local PulseAudio/PipeWire development headers (`portaudio19-dev`). In containers or headless environments, text input mode is used automatically.