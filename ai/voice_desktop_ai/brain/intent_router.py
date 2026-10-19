from dataclasses import dataclass, field
import re

from brain.intent import Intent, parse_intent
from computer.keyboard import parse_shortcut


CONVERSATION = "conversation"
COMPUTER_ACTION = "computer_action"
WEB_NAVIGATION = "web_navigation"
SYSTEM_CONTROL = "system_control"
MIXED = "mixed"
AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class RoutedIntent:
    route: str
    original_text: str
    normalized_text: str
    semantic_intent: str = ""
    language: str = "unknown"
    confidence: float = 0.0
    conversation_text: str = ""
    computer_goal: str = ""
    legacy_intent: Intent | None = None
    clarification: str = ""
    parts: tuple = field(default_factory=tuple)
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "route": self.route,
            "original_text": self.original_text,
            "normalized_text": self.normalized_text,
            "semantic_intent": self.semantic_intent,
            "language": self.language,
            "confidence": self.confidence,
            "conversation_text": self.conversation_text,
            "computer_goal": self.computer_goal,
            "legacy_intent": self.legacy_intent.action if self.legacy_intent else None,
            "clarification": self.clarification,
            "parts": list(self.parts),
            "metadata": dict(self.metadata),
        }


class IntentRouter:
    """Classify user goals before any computer-control path is reached."""

    def route(self, transcript):
        original = str(transcript or "").strip()
        normalized = normalize_goal_text(original)
        language = detect_language(original, normalized)
        text = strip_assistant_name(normalized)

        if not text:
            return RoutedIntent(
                AMBIGUOUS,
                original,
                normalized,
                language=language,
                clarification="Please tell me what you want Maruti to do.",
            )

        if text in {"stop", "exit", "quit", "goodbye", "close assistant"}:
            return RoutedIntent(
                COMPUTER_ACTION,
                original,
                text,
                semantic_intent="exit",
                confidence=1.0,
                computer_goal=original,
                legacy_intent=Intent("exit"),
            )
        if text in {"shutdown", "shut down"}:
            return RoutedIntent(
                COMPUTER_ACTION,
                original,
                text,
                semantic_intent="shutdown",
                confidence=1.0,
                computer_goal=original,
                legacy_intent=Intent("shutdown"),
            )

        if _is_acknowledgement_phrase(text):
            return RoutedIntent(
                AMBIGUOUS,
                original,
                normalized,
                language=language,
                clarification="",
            )

        greeting = greeting_intent(text)
        if greeting:
            return RoutedIntent(
                CONVERSATION,
                original,
                normalized,
                semantic_intent=greeting,
                language=language,
                confidence=0.95,
                conversation_text=original,
            )

        click_command = re.search(r"\b(?:click|double\s+click|right\s+click)\b", text)
        web = None if click_command else web_navigation_intent(text)
        if web:
            return RoutedIntent(
                WEB_NAVIGATION,
                original,
                text,
                semantic_intent="open_website",
                language=language,
                confidence=web["confidence"],
                computer_goal=original,
                metadata={"target": web["target"]},
            )

        full_screen_screenshot = re.search(
            r"\b(?:take|capture|full|poori|puri)\b.*\b(?:full screen|whole screen|entire screen|screen screenshot|screen capture|screen ka screenshot)\b"
            r"|\b(?:take|capture)\s+(?:the\s+)?(?:whole|entire)\s+screen\b",
            text,
        )
        if full_screen_screenshot:
            return RoutedIntent(
                COMPUTER_ACTION,
                original,
                text,
                semantic_intent="screenshot_start",
                language=language,
                confidence=0.98,
                computer_goal=original,
                legacy_intent=Intent("screenshot_start"),
                metadata={"action": "take_screenshot", "mode": "full_screen"},
            )

        system = system_control_intent(text)
        computer = computer_intent(text)
        conversation = conversation_intent(text)

        if computer and computer["semantic_intent"] in {
            "click_visual_target", "right_click", "mouse_down", "mouse_up", "mouse_move",
        }:
            return RoutedIntent(
                COMPUTER_ACTION,
                original,
                text,
                semantic_intent=computer["semantic_intent"],
                language=language,
                confidence=computer["confidence"],
                computer_goal=original,
                legacy_intent=computer.get("legacy_intent"),
                metadata=computer.get("metadata", {}),
            )

        if system:
            metadata = dict(system.get("metadata", {}))
            metadata.setdefault("goal", original)
            return RoutedIntent(
                SYSTEM_CONTROL,
                original,
                text,
                semantic_intent=system["semantic_intent"],
                language=language,
                confidence=system["confidence"],
                computer_goal=original,
                metadata=metadata,
            )

        if computer and conversation and not conversation.get("metadata", {}).get("fallback"):
            return RoutedIntent(
                MIXED,
                original,
                normalized,
                semantic_intent="mixed_computer_and_conversation",
                language=language,
                confidence=0.8,
                conversation_text=original,
                computer_goal=original,
                clarification=(
                    "I heard both a computer action and a question. "
                    "Please tell me which one to handle first."
                ),
                parts=(
                    {"route": COMPUTER_ACTION, "semantic_intent": computer["semantic_intent"]},
                    {"route": CONVERSATION, "semantic_intent": conversation["semantic_intent"]},
                ),
                metadata={"router_only": True},
            )

        if conversation and not computer:
            return RoutedIntent(
                CONVERSATION,
                original,
                normalized,
                semantic_intent=conversation["semantic_intent"],
                language=language,
                confidence=conversation["confidence"],
                conversation_text=original,
                metadata=conversation.get("metadata", {}),
            )

        if computer:
            canonical = computer["canonical"]
            return RoutedIntent(
                COMPUTER_ACTION,
                original,
                canonical,
                semantic_intent=computer["semantic_intent"],
                language=language,
                confidence=computer["confidence"],
                computer_goal=original,
                legacy_intent=computer.get("legacy_intent"),
                metadata=computer.get("metadata", {}),
            )

        if _is_bare_topic(text):
            return RoutedIntent(
                AMBIGUOUS,
                original,
                normalized,
                language=language,
                clarification="",
            )

        return RoutedIntent(
            AMBIGUOUS,
            original,
            normalized,
            language=language,
            clarification="I am not sure whether this is a question or a computer action.",
        )


def normalize_goal_text(transcript):
    text = str(transcript or "").strip().lower()
    text = text.replace("?", " ? ")
    text = text.replace("।", " ")
    replacements = (
        ("मारुति", "maruti"),
        ("क्रोम", "chrome"),
        ("गूगल क्रोम", "google chrome"),
        ("यूट्यूब", "youtube"),
        ("वाईफाई", "wifi"),
        ("वाई फाई", "wifi"),
        ("ब्लूटूथ", "bluetooth"),
        ("ब्लू टूथ", "bluetooth"),
        ("bluetooh", "bluetooth"),
        ("bluetooth", "bluetooth"),
        ("wi fi", "wifi"),
        ("wif i", "wifi"),
        ("you tube", "youtube"),
        ("d chrome", "chrome"),
        ("chrome", "chrome"),
        ("खोल दो", "open"),
        ("खोलो", "open"),
        ("खोलना", "open"),
        ("ओपन", "open"),
        ("क्लिक", "click"),
        ("दबाओ", "press"),
        ("एंटर", "enter"),
        ("इंटर", "enter"),
        ("नीचे", "down"),
        ("ऊपर", "up"),
        ("स्क्रॉल", "scroll"),
        ("स्क्रोल", "scroll"),
        ("रीलोड", "reload"),
        ("प्रधानमंत्री", "prime minister"),
        ("कौन हैं", "who is"),
        ("कौन है", "who is"),
        ("कौन", "who"),
        ("क्या है", "what is"),
        ("क्या", "what"),
        ("कैसे हो", "how are you"),
        ("नमस्ते", "hello"),
        ("समाचार", "news"),
        ("खबर", "news"),
        ("बताओ", "tell"),
        ("भारत", "india"),
        ("aaj", "today"),
        ("kholo", "open"),
        ("khol do", "open"),
        ("khol", "open"),
        ("open karo", "open"),
        ("open kar do", "open"),
        ("click karo", "click"),
        ("press karo", "press"),
        ("search karo", "search"),
        ("reload karo", "reload"),
        ("scroll karo", "scroll"),
        ("neeche", "down"),
        ("niche", "down"),
        ("upar", "up"),
        ("kaun hai", "who is"),
        ("kaun hain", "who is"),
        ("kya hai", "what is"),
        ("kaise ho", "how are you"),
        ("ke baare mein", "about"),
        ("batao", "tell"),
        ("aur", "and"),
        ("phir", "then"),
        ("mujhe", ""),
        ("please", ""),
        ("bhai", ""),
        ("karo", ""),
        ("kar do", ""),
        ("par", "on"),
        ("chalu", "on"),
        ("chaloo", "on"),
        ("band", "off"),
        ("बंद", "off"),
        ("चालू", "on"),
        ("on karo", "on"),
        ("off karo", "off"),
        ("on kar do", "on"),
        ("off kar do", "off"),
        ("back jao", "go back"),
        ("peeche jao", "go back"),
        ("go backward", "go back"),
        ("backward", "back"),
    )
    for source, replacement in replacements:
        text = text.replace(source, replacement)
    text = re.sub(r"\bctrl\s*\+\s*r\b", "ctrl+r", text)
    if not re.match(r"^\s*(?:maruti\s+)?press\b", text):
        text = re.sub(r"[,:;.!]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_language(original, normalized):
    if re.search(r"[\u0900-\u097f]", original):
        if re.search(r"[a-zA-Z]", original):
            return "hindi_english_mixed"
        return "hindi"
    hinglish_markers = {"kholo", "khol", "karo", "kaun", "kya", "batao", "neeche", "niche", "bhai", "par"}
    words = set(re.findall(r"[a-z]+", original.lower()))
    if words & hinglish_markers:
        return "hinglish"
    return "english" if normalized else "unknown"


def strip_assistant_name(text):
    text = re.sub(r"^\s*maruti\b", "", text).strip()
    text = re.sub(r"\bmaruti\s*$", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def greeting_intent(text):
    if text in {"hello", "hi", "hey", "namaste"}:
        return "hello"
    if "how are you" in text:
        return "how_are_you"
    return ""


def _is_acknowledgement_phrase(text):
    ack_phrases = {
        "okay", "ok", "i understand", "okay i understand", "understood", "got it",
        "alright", "fine", "hmm okay", "haan samajh gaya", "theek hai", "samajh gaya",
    }
    return text in ack_phrases or any(phrase in text for phrase in ("i understand", "understood", "got it", "samajh gaya", "theek hai"))


def _is_bare_topic(text):
    words = re.findall(r"[a-z0-9]+", text)
    if not words:
        return True

    explicit_markers = {
        "what", "who", "when", "where", "why", "how", "tell", "about", "weather",
        "write", "code", "program", "open", "click", "press", "type", "search",
        "scroll", "copy", "paste", "close", "minimize", "maximize", "switch", "go",
        "next", "previous", "settings", "chrome", "gmail", "youtube", "google", "samjhao",
        "batao", "kaun", "kya", "hai", "kar", "karo", "kholo", "on", "off", "bluetooth",
        "wifi", "brightness", "volume", "tab",
    }
    if any(word in words for word in explicit_markers):
        return False
    if any(marker in text for marker in {"?", " tell ", " about ", "who ", "what ", "when ", "where ", "why ", "how "}):
        return False

    if len(words) == 1:
        return words[0] in {"tesla", "nehru", "yadav", "lassi", "bahubali", "nikon", "braces", "window"}

    if len(words) <= 2 and all(re.fullmatch(r"[a-z]+", w) for w in words):
        return words[0] not in {"maruti"} and words[0] not in explicit_markers and words[1] not in explicit_markers

    return False


def conversation_intent(text):
    if greeting_intent(text):
        return {"semantic_intent": greeting_intent(text), "confidence": 0.95}
    if _is_acknowledgement_phrase(text) or _is_bare_topic(text):
        return None
    question_markers = (
        "who", "what", "when", "where", "why", "how",
        "prime minister", "news", "movie", "about", "tell", "today",
        "explain", "samjhao", "samjha", "owner", "company", "date", "weather",
        "write", "code", "program", "current", "who is", "what is",
    )
    if text.startswith(("open ", "kholo ", "launch ")) and not any(q in text for q in ("who", "what", "when", "where", "why", "how", "explain", "tell", "?")):
        return None
    if "?" in text or any(marker in text for marker in question_markers):
        return {
            "semantic_intent": "informational_question",
            "confidence": 0.9,
            "metadata": {"provider_required": True},
        }
    explicit_computer_words = {
        "open", "click", "press", "scroll", "type", "copy", "paste", "select", "search",
        "play", "minimize", "close", "forward", "back", "enter", "caps", "screenshot",
    }
    protected_nouns = {"chrome", "youtube", "gmail", "settings", "button", "file"}
    words = set(re.findall(r"[a-z]+", text))
    if words and not words & explicit_computer_words and not words <= protected_nouns:
        return {
            "semantic_intent": "general_conversation",
            "confidence": 0.55,
            "metadata": {"provider_required": True, "fallback": True},
        }
    return None


def web_navigation_intent(text):
    """Recognize only explicit requests to open a website."""
    if re.fullmatch(r"(?:open\s+web|open\s+(?:the\s+)?website(?:\s+of)?|website)", text):
        return {"target": "", "confidence": 0.98}
    par_match = re.match(r"^web\s+(?:par|on)\s+(.+?)\s+(?:kholo|open)$", text)
    if par_match:
        return {"target": par_match.group(1).strip(), "confidence": 0.98}
    if re.match(r"^open\s+(?:my\s+)?physics\s+(?:wala|wallah)$", text):
        return {"target": "physics wallah", "confidence": 0.98}
    patterns = (
        r"\bopen\s+web\s+(.+)$",
        r"\bweb\s+open\s+(.+)$",
        r"\bopen\s+(?:the\s+)?website(?:\s+of)?\s+(.+)$",
        r"\bwebsite\s+open\s+(.+)$",
        r"\bweb\s+kholo\s+(.+)$",
        r"\bwebsite\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            target = match.group(1).strip().removesuffix(" kholo").strip()
            return {"target": target, "confidence": 0.98} if target else None
    return None


def system_control_intent(text):
    words = set(re.findall(r"[a-z0-9]+", text.replace("_", " ")))

    if "bluetooth" in words or "bluetooth" in text:
        value = _extract_toggle_value(text)
        if value is not None:
            return {
                "semantic_intent": "system_control_bluetooth",
                "confidence": 0.98,
                "metadata": {"system_action": "bluetooth", "operation": "set", "value": value, "goal": text},
            }

    if "wifi" in words or "wi" in words and "fi" in words:
        value = _extract_toggle_value(text)
        if value is not None:
            return {
                "semantic_intent": "system_control_wifi",
                "confidence": 0.98,
                "metadata": {"system_action": "wifi", "operation": "set", "value": value, "goal": text},
            }

    if "brightness" in words:
        numeric = _extract_numeric_value(text)
        if numeric is not None:
            return {
                "semantic_intent": "system_control_brightness",
                "confidence": 0.98,
                "metadata": {"system_action": "brightness", "operation": "set", "value": numeric, "goal": text},
            }
        if "set" in words:
            return {
                "semantic_intent": "system_control_brightness",
                "confidence": 0.95,
                "metadata": {"system_action": "brightness", "operation": "set", "value": None, "goal": text},
            }

    if "volume" in words:
        numeric = _extract_numeric_value(text)
        if numeric is not None:
            return {
                "semantic_intent": "system_control_volume",
                "confidence": 0.98,
                "metadata": {"system_action": "volume", "operation": "set", "value": numeric, "goal": text},
            }
        if "mute" in words or "muted" in words:
            return {
                "semantic_intent": "system_control_volume",
                "confidence": 0.98,
                "metadata": {"system_action": "volume", "operation": "set", "value": "mute", "goal": text},
            }
        if "unmute" in words:
            return {
                "semantic_intent": "system_control_volume",
                "confidence": 0.98,
                "metadata": {"system_action": "volume", "operation": "set", "value": "unmute", "goal": text},
            }

    if "mute" in words and "volume" not in words:
        return {
            "semantic_intent": "system_control_volume",
            "confidence": 0.98,
            "metadata": {"system_action": "volume", "operation": "set", "value": "mute", "goal": text},
        }

    if "unmute" in words:
        return {
            "semantic_intent": "system_control_volume",
            "confidence": 0.98,
            "metadata": {"system_action": "volume", "operation": "set", "value": "unmute", "goal": text},
        }

    if "settings" in words or "setting" in words:
        if "display" in words:
            return {"semantic_intent": "system_control_settings", "confidence": 0.97, "metadata": {"system_action": "display", "operation": "open", "value": None, "goal": text}}
        if "sound" in words or "audio" in words:
            return {"semantic_intent": "system_control_settings", "confidence": 0.97, "metadata": {"system_action": "sound", "operation": "open", "value": None, "goal": text}}
        return {"semantic_intent": "system_control_settings", "confidence": 0.97, "metadata": {"system_action": "settings", "operation": "open", "value": None, "goal": text}}

    if "display" in words and "settings" in words:
        return {"semantic_intent": "system_control_settings", "confidence": 0.97, "metadata": {"system_action": "display", "operation": "open", "value": None, "goal": text}}

    if "sound" in words and "settings" in words:
        return {"semantic_intent": "system_control_settings", "confidence": 0.97, "metadata": {"system_action": "sound", "operation": "open", "value": None, "goal": text}}

    if "open" in words and ("settings" in words or "setting" in words):
        return {"semantic_intent": "system_control_settings", "confidence": 0.97, "metadata": {"system_action": "settings", "operation": "open", "value": None, "goal": text}}

    return None


def _extract_toggle_value(text):
    if re.search(r"\b(turn\s+)?(?:bluetooth|wifi)\s+(?:on|enable|chalu|active)\b", text):
        return "on"
    if re.search(r"\b(turn\s+)?(?:bluetooth|wifi)\s+(?:off|disable|band|inactive)\b", text):
        return "off"
    if re.search(r"\b(?:on|enable|chalu|active)\b", text) and ("bluetooth" in text or "wifi" in text):
        return "on"
    if re.search(r"\b(?:off|disable|band|inactive)\b", text) and ("bluetooth" in text or "wifi" in text):
        return "off"
    return None


def _extract_numeric_value(text):
    match = re.search(r"\b(\d{1,3})\b", text)
    if match:
        return int(match.group(1))
    return None


def computer_intent(text):
    words = set(re.findall(r"[a-z0-9+]+", text))

    if web_navigation_intent(text) and not re.search(r"\b(?:click|double\s+click|right\s+click)\b", text):
        return None

    if re.search(r"\b(select all|select everything|sab select|pura select|sab kuch select|select all text)\b", text):
        return _computer(
            "select_all",
            "select all",
            legacy_intent=Intent("select_all"),
            metadata={"action": "select_all", "keys": ["ctrl", "a"]},
        )

    if re.search(r"\b(copy|cut|paste)\b", text) and not re.search(r"\b(select all|select everything|sab select|pura select)\b", text):
        if "copy" in words:
            return _computer("copy", "copy", legacy_intent=Intent("copy"))
        if "cut" in words:
            return _computer("cut", "cut", legacy_intent=Intent("cut"))
        if "paste" in words:
            return _computer("paste", "paste", legacy_intent=Intent("paste"))

    if re.search(r"\bplay\b", text):
        query = text.replace("play", "", 1).strip()
        canonical = f"play {query}" if query else "play"
        return _computer("media_play", canonical, legacy_intent=Intent("search", value=query), metadata={"value": query})

    if "ctrl+r" in words or ("ctrl" in words and "r" in words):
        return _computer("reload_page", "ctrl+r", metadata={"action": "hotkey", "keys": ["ctrl", "r"]})

    if "reload" in words:
        return _computer("reload_page", "reload page")

    if re.search(r"\b(switch to next window|switch on next window|next window|go to next window)\b", text):
        return _computer(
            "next_window",
            "next window",
            legacy_intent=Intent("hotkey", metadata={"keys": ["alt", "tab"]}),
            metadata={"action": "hotkey", "keys": ["alt", "tab"]},
        )

    if re.search(r"\bswitch(?: the)? window\b", text):
        return _computer(
            "switch_window",
            "switch window",
            legacy_intent=Intent("hotkey", metadata={"keys": ["alt", "tab"]}),
            metadata={"action": "hotkey", "keys": ["alt", "tab"]},
        )

    shortcut_keys = _shortcut_keys_for_text(text)
    if shortcut_keys:
        if len(shortcut_keys) == 1:
            key = shortcut_keys[0]
            return _computer(
                "keyboard_press",
                "keyboard press",
                legacy_intent=Intent("press", value=key),
                metadata={"action": "press", "key": key, "raw_text": text},
            )
        return _computer(
            "keyboard_shortcut",
            "keyboard shortcut",
            legacy_intent=Intent("hotkey", metadata={"keys": shortcut_keys}),
            metadata={"action": "hotkey", "keys": shortcut_keys, "raw_text": text},
        )

    if "scroll" in words and "down" in words:
        return _computer("scroll_down", "scroll down", legacy_intent=Intent("scroll_down"))
    if "scroll" in words and "up" in words:
        return _computer("scroll_up", "scroll up", legacy_intent=Intent("scroll_up"))

    right_click_match = re.search(r"\bright(?:\s+mouse)?\s+click(?:\s+on)?(?:\s+the)?\s+(.+)$", text)
    right_click_before_match = re.search(r"^(.+?)\s+(?:par|on)\s+right(?:\s+mouse)?\s+click", text)
    if right_click_before_match:
        target = _clean_target(right_click_before_match.group(1)) or "current"
        return _computer("right_click", "right click", legacy_intent=Intent("right_click", target=target), metadata={"action": "right_click", "target": target})
    if right_click_match:
        target = _clean_target(right_click_match.group(1)) or "current"
        return _computer("right_click", "right click", legacy_intent=Intent("right_click", target=target), metadata={"action": "right_click", "target": target})

    if re.search(r"\b(?:open|kholo|khol do|open karo)\b.*\b(?:and|aur)\b.*\b(?:chrome|edge|word|notepad|code|vscode|explorer)\b", text):
        apps = []
        for app in ["chrome", "edge", "word", "notepad", "code", "vscode", "explorer", "file explorer"]:
            if app in text:
                apps.append(app)
        if len(apps) >= 2:
            return _computer("open_multiple_applications", "open multiple applications", legacy_intent=Intent("open_multiple_applications"), metadata={"action": "open_multiple_applications", "applications": apps})

    if re.search(r"\b(open .* and .*|.* aur .* dono kholo|.* aur .* ko side by side kholo|.* and .* side by side)\b", text):
        apps = []
        for part in re.split(r"\s+and\s+|\s+aur\s+|\s+dono\s+|\s+both\s+", text):
            cleaned = part.replace("open", "").replace("khol", "").replace("karo", "").replace("kholo", "").strip()
            if cleaned:
                apps.append(cleaned)
        apps = [item for item in apps if item and item not in {"", "open"}]
        if len(apps) >= 2:
            return _computer("open_multiple_applications", "open multiple applications", legacy_intent=Intent("open_multiple_applications"), metadata={"action": "open_multiple_applications", "applications": [app.split()[0] if len(app.split()) > 1 else app for app in apps]})

    if re.search(r"\b(open|kholo|khol do|open karo)\b", text):
        app_target = None
        for alias in ["file explorer", "explorer", "vs code", "vscode", "visual studio code", "microsoft edge", "edge", "chrome", "google chrome", "word", "microsoft word", "notepad", "note pad"]:
            if alias in text:
                app_target = alias
                break
        if app_target:
            app_name = app_target.replace("visual studio code", "vscode").replace("microsoft edge", "edge").replace("google chrome", "chrome").replace("microsoft word", "word").replace("note pad", "notepad")
            semantic = "open_chrome" if app_name == "chrome" else "open_application"
            return _computer(semantic, "open chrome" if semantic == "open_chrome" else "open application", legacy_intent=Intent("open_application", target=app_name), metadata={"action": "open_application", "application": app_name})

    if "enter" in words and ("click" in words or "press" in words):
        canonical = "click enter button" if "click" in words else "enter"
        legacy = parse_intent(canonical)
        return _computer("click_enter_button", canonical, legacy_intent=legacy)

    if "click" in words and not re.search(r"\b(?:hold|release|unhold|press and hold)\b", text):
        target = _target_after(text, "click") or _target_before(text, "click")
        if not target:
            return None
        canonical = "click " + (target or "target")
        return _computer(
            "click_visual_target",
            canonical,
            legacy_intent=parse_intent(canonical),
            metadata={"target": target},
        )

    if "open" in words and "chrome" in words:
        return _computer(
            "open_chrome",
            "open chrome",
            legacy_intent=Intent("open", target="chrome"),
            metadata={"target": "chrome"},
        )

    if "close" in words and "chrome" in words:
        return _computer(
            "close_chrome",
            "close chrome",
            legacy_intent=Intent("close", target="chrome"),
            metadata={"target": "chrome"},
        )

    if re.search(r"\b(take screenshot|screenshot|screen shot|screen capture|capture screen|screenshot le lo|screen ki photo lo|screen capture karo|screen shot lo|screenshot karo|take a screenshot)\b", text):
        return _computer("screenshot_start", "screenshot start", legacy_intent=Intent("screenshot_start"), metadata={"action": "screenshot_start"})

    mouse = mouse_intent(text)
    if mouse:
        return mouse

    if re.search(r"\b(caps lock|caps on|caps off|caps lock on|caps lock off|caps on karo|caps off karo|caps band karo|caps chalu karo)\b", text):
        state = "on" if "on" in text or "chalu" in text or "active" in text else "off"
        return _computer("caps_lock", "caps lock", legacy_intent=Intent("caps_lock", target=state), metadata={"action": "caps_lock", "state": state})

    if re.search(r"\b(minimize|minimise|minize|minimize this window|minimise this window|minize this window|minimize window|minimise window|minize window|window minimize|window minimise|window minize|current window minimize|current window minimise|is window ko minimize|is window ko minimise|window minimize karo|window minimise karo|window minize karo|minimize karo|minimise karo|minize karo)\b", text):
        return _computer("minimize_window", "minimize window", legacy_intent=Intent("minimize_window", target="current"), metadata={"action": "minimize_window", "target": "current"})

    if re.search(r"\b(restore window|window restore|minimized window wapas lao|restore karo|restore the window)\b", text):
        return _computer("restore_window", "restore window", legacy_intent=Intent("restore_window"), metadata={"action": "restore_window"})

    if re.search(r"\b(right click|right mouse click|right click here|right click on|file par right click|is button par right click|right click karo)\b", text):
        target = "current"
        if re.search(r"\b(file|button|window|link|menu)\b", text):
            target = _clean_target(text.replace("right click", "").replace("karo", "").replace("here", "").strip()) or "current"
        return _computer("right_click", "right click", legacy_intent=Intent("right_click", target=target), metadata={"action": "right_click", "target": target})

    if re.search(r"\b(open .* and .*|.* aur .* dono kholo|.* aur .* ko side by side kholo|.* and .* side by side)\b", text):
        apps = []
        for part in re.split(r"\s+and\s+|\s+aur\s+|\s+dono\s+|\s+both\s+", text):
            cleaned = part.replace("open", "").replace("khol", "").replace("karo", "").replace("kholo", "").strip()
            if cleaned:
                apps.append(cleaned)
        apps = [item for item in apps if item and item not in {"", "open"}]
        if len(apps) >= 2:
            return _computer("open_multiple_applications", "open multiple applications", legacy_intent=Intent("open_multiple_applications"), metadata={"action": "open_multiple_applications", "applications": [app.split()[0] if len(app.split()) > 1 else app for app in apps]})

    if "side by side" in text:
        windows = []
        for token in ["chrome", "edge", "word", "notepad", "code"]:
            if token in text:
                windows.append(token)
        return _computer("arrange_windows", "arrange windows side by side", legacy_intent=Intent("arrange_windows"), metadata={"action": "arrange_windows", "layout": "side_by_side", "windows": windows or ["chrome", "edge"]})

    if re.search(r"\b(open|kholo|khol do|open karo)\b", text):
        app_target = None
        for alias in ["file explorer", "explorer", "vs code", "vscode", "visual studio code", "microsoft edge", "edge", "chrome", "google chrome", "word", "microsoft word", "notepad", "note pad"]:
            if alias in text:
                app_target = alias
                break
        if app_target:
            app_name = app_target.replace("visual studio code", "vscode").replace("microsoft edge", "edge").replace("google chrome", "chrome").replace("microsoft word", "word").replace("note pad", "notepad")
            semantic = "open_chrome" if app_name == "chrome" else "open_application"
            return _computer(semantic, "open chrome" if semantic == "open_chrome" else "open application", legacy_intent=Intent("open_application", target=app_name), metadata={"action": "open_application", "application": app_name})

    if text in {"close window", "close the window"}:
        return _computer("close_window", text, legacy_intent=Intent("close_window"))

    if text in {"shut down", "shutdown"}:
        return _computer("shutdown", text, legacy_intent=Intent("shutdown"))

    if "open" in words and "tab" in words:
        return _computer("open_tab", "open new tab", legacy_intent=Intent("open_tab"))
    if "close" in words and "tab" in words:
        return _computer("close_tab", "close tab", legacy_intent=Intent("close_tab"))

    if "youtube" in words and ("open" in words or "search" in words):
        return _computer("multi_step_computer_action", text, metadata={"target": "youtube"})

    if "search" in words and not conversation_intent(text):
        value = text.split("search", 1)[0].strip() or text.split("search", 1)[1].strip()
        if not value:
            return None
        canonical = "search " + value if value else "search"
        return _computer("search", canonical, legacy_intent=parse_intent(canonical), metadata={"value": value})

    if text in {"back", "go back"}:
        return _computer("back", "back", legacy_intent=Intent("back"))
    if text in {"forward", "go forward"}:
        return _computer("forward", "forward", legacy_intent=Intent("forward"))

    if "chrome" in words or "youtube" in words:
        return None

    if re.search(r"\b(select from|select from .* to .*|hello se .* tak select|.* se .* tak select)\b", text):
        match = re.search(r"select from\s+(.+?)\s+to\s+(.+)$|(.+?)\s+se\s+(.+?)\s+tak\s+select", text)
        if match:
            start = (match.group(1) or match.group(3) or "").strip()
            end = (match.group(2) or match.group(4) or "").strip()
            if start and end:
                return _computer(
                    "select_text_range",
                    "select text range",
                    legacy_intent=Intent("select_text_range"),
                    metadata={"start_text": start, "end_text": end},
                )

    legacy = parse_intent(text)
    if legacy and legacy.action not in {"hello", "how_are_you"}:
        if legacy.action in {"click", "double_click", "right_click", "search", "type"} and not (legacy.target or legacy.value):
            return None
        return _computer(legacy.action, text, legacy_intent=legacy)

    return None


def mouse_intent(text):
    amount_match = re.search(r"\b(\d+)\b", text)
    amount = int(amount_match.group(1)) if amount_match else None
    if re.search(r"\b(?:hold left click|hold left mouse button|press and hold left click|left button down|left button dabao|mouse button down)\b", text):
        return _computer("mouse_down", "mouse down", legacy_intent=Intent("mouse_down"), metadata={"action": "mouse_down", "button": "left"})
    if re.search(r"\b(?:unhold left click|unhold left button|release left click|release left mouse button|left button up|left button chhodo|mouse button up)\b", text):
        return _computer("mouse_up", "mouse up", legacy_intent=Intent("mouse_up"), metadata={"action": "mouse_up", "button": "left"})
    if re.search(r"\bright click\b", text):
        return _computer("right_click", "right click", legacy_intent=Intent("right_click"), metadata={"action": "right_click"})
    if re.search(r"\bdouble click\b", text):
        return _computer("double_click", "double click", legacy_intent=Intent("double_click"), metadata={"action": "double_click"})
    direction = next((item for item in ("right", "left", "up", "down") if re.search(rf"\b{item}\b", text)), None)
    if direction and ("mouse" in text or text.strip() in {direction, f"go {direction}"}):
        return _computer("mouse_move", "mouse move", legacy_intent=Intent("mouse_move"), metadata={"action": "mouse_move", "direction": direction, "amount": amount})
    return None


def _shortcut_keys_for_text(text):
    keys = parse_shortcut(text)
    if not keys:
        return []
    if any(token in {"copy", "cut", "paste", "select"} for token in keys):
        return []
    return keys


def _computer(semantic_intent, canonical, legacy_intent=None, metadata=None):
    return {
        "semantic_intent": semantic_intent,
        "canonical": canonical,
        "confidence": 0.9,
        "legacy_intent": legacy_intent,
        "metadata": dict(metadata or {}),
    }


def _target_after(text, action):
    match = re.search(rf"\b{re.escape(action)}\b(?:\s+on)?(?:\s+the)?\s+(.+)$", text)
    if not match:
        return ""
    return _clean_target(match.group(1))


def _target_before(text, action):
    before = text.split(action, 1)[0].strip()
    return _clean_target(before)


def _clean_target(value):
    value = str(value or "")
    value = value.strip()
    value = re.sub(r"^(?:please\s+)?(?:on\s+)?(?:the\s+)?", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^(?:click|double click|right click)\s+", "", value, flags=re.IGNORECASE)

    for _ in range(4):
        cleaned = value
        cleaned = re.sub(
            r"\s+(?:button|btn|logo|icon|text|label|link|menu|tab|item|tile|window|page|pane|panel|card|section|header|footer|toolbar|title|field|box|checkbox|radio|toggle|dialog|popup|search bar)\b.*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\s+(?:in|at|on|near|by|beside|under|over)\s+(?:the\s+)?(?:top|bottom|left|right|center|middle|sidebar|menu|toolbar|panel|header|footer|corner|screen|page|window|browser)(?:\s+(?:left|right|top|bottom|center|middle|side|corner))?.*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+(?:please|on|par|karo|kar do|do)\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\n\r-_")
        if not cleaned:
            return ""
        if cleaned == value:
            return cleaned
        value = cleaned
    return value
