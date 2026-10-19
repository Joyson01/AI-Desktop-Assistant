import re

try:
    import pyautogui
except Exception:
    pyautogui = None

KEY_ALIASES = {
    "control": "ctrl",
    "ctrl": "ctrl",
    "command": "ctrl",
    "windows": "win",
    "window": "win",
    "window key": "win",
    "win": "win",
    "function": "fn",
    "fn": "fn",
    "super": "win",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "escape": "esc",
    "esc": "esc",
    "enter": "enter",
    "return": "enter",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "tab": "tab",
    "space": "space",
    "spacebar": "space",
    "page up": "pageup",
    "pageup": "pageup",
    "page down": "pagedown",
    "pagedown": "pagedown",
    "arrow up": "up",
    "up arrow": "up",
    "arrow down": "down",
    "down arrow": "down",
    "arrow left": "left",
    "left arrow": "left",
    "arrow right": "right",
    "right arrow": "right",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "printscreen": "printscreen",
    "prtscr": "printscreen",
    "контрол": "ctrl",
    "कंट्रोल": "ctrl",
    "शिफ्ट": "shift",
    "ऑल्ट": "alt",
    "एंटर": "enter",
    "टैब": "tab",
    "स्पेस": "space",
    "डिलीट": "delete",
    "बैकस्पेस": "backspace",
    "बैक स्पेस": "backspace",
    "विंडोज": "win",
}

SHIFTED_CHARACTERS = {
    "1": "!",
    "2": "@",
    "3": "#",
    "4": "$",
    "5": "%",
    "6": "^",
    "7": "&",
    "8": "*",
    "9": "(",
    "0": ")",
    "a": "A",
    "b": "B",
    "c": "C",
    "d": "D",
    "e": "E",
    "f": "F",
    "g": "G",
    "h": "H",
    "i": "I",
    "j": "J",
    "k": "K",
    "l": "L",
    "m": "M",
    "n": "N",
    "o": "O",
    "p": "P",
    "q": "Q",
    "r": "R",
    "s": "S",
    "t": "T",
    "u": "U",
    "v": "V",
    "w": "W",
    "x": "X",
    "y": "Y",
    "z": "Z",
    "`": "~",
    "-": "_",
    "=": "+",
    "[": "{",
    "]": "}",
    "\\": "|",
    ";": ":",
    "'": '"',
    ",": "<",
    ".": ">",
    "/": "?",
}

KEY_ALIASES_BY_LENGTH = sorted(KEY_ALIASES, key=len, reverse=True)
KEYWORD_STOPWORDS = {
    "press", "pressed", "dabao", "daba", "karo", "kar", "do", "aur", "and", "then",
    "please", "the", "on", "of", "to", "from", "into", "after", "before",
    "this", "that", "here", "there", "select", "copy", "cut", "paste",
    "all", "everything", "text", "word", "words", "button", "sab", "pura", "kuch",
    "what", "which", "where", "why", "how",
}
MODIFIER_KEYS = {"ctrl", "shift", "alt", "win", "esc", "enter", "tab", "space", "delete", "backspace", "up", "down", "left", "right", "home", "end", "pageup", "pagedown"}


def _normalize_key_token(token):
    cleaned = " ".join(str(token or "").strip().lower().split())
    if not cleaned:
        return ""
    if cleaned in KEY_ALIASES:
        return KEY_ALIASES[cleaned]
    if cleaned.endswith("+"):
        cleaned = cleaned[:-1].strip()
    return cleaned


def parse_shortcut(text):
    if not text or not str(text).strip():
        return []

    normalized = str(text).lower().replace("&", " + ").replace("plus", " + ")
    normalized = normalized.replace("–", "-").replace("—", "-")
    normalized = normalized.replace("कंट्रोल", "control").replace("शिफ्ट", "shift")
    normalized = normalized.replace("ऑल्ट", "alt").replace("एंटर", "enter")
    normalized = normalized.replace("टैब", "tab").replace("स्पेस", "space")
    normalized = normalized.replace("डिलीट", "delete").replace("बैकस्पेस", "backspace")
    normalized = normalized.replace("बैक स्पेस", "backspace")
    normalized = normalized.replace("विंडोज", "windows")
    normalized = normalized.replace("ए", "a").replace("बी", "b").replace("सी", "c").replace("डी", "d")
    normalized = normalized.replace("ई", "e").replace("एफ", "f").replace("जी", "g").replace("एच", "h")
    normalized = normalized.replace("आई", "i").replace("जे", "j").replace("के", "k").replace("एल", "l")
    normalized = normalized.replace("एम", "m").replace("एन", "n").replace("ओ", "o").replace("पी", "p")
    normalized = normalized.replace("क्यू", "q").replace("आर", "r").replace("एस", "s").replace("टी", "t")
    normalized = normalized.replace("यू", "u").replace("वी", "v").replace("डब्ल्यू", "w").replace("एक्स", "x")
    normalized = normalized.replace("वाई", "y").replace("जेड", "z")
    normalized = re.sub(r"\bwindow\s+key\b", "win", normalized)
    normalized = re.sub(r"\s*\+\s*", " + ", normalized)
    tokens = re.findall(r"[a-z0-9]+|[^\s]", normalized)
    if not tokens:
        return []

    explicit = {"ctrl", "control", "shift", "alt", "win", "window", "windows", "fn", "function", "esc", "enter", "tab", "delete", "backspace", "space", "pageup", "pagedown", "up", "down", "left", "right", "home", "end"}
    modifiers = {"ctrl", "control", "shift", "alt", "win", "windows", "esc"}
    if not (
        "press" in tokens
        or "+" in normalized
        or any(token in modifiers for token in tokens)
    ):
        return []

    keys = []
    for index, token in enumerate(tokens):
        if token in {"press", "pressed", "dabao", "daba", "karo", "kar", "do", "aur", "and", "then", "please", "the", "on", "of", "to", "from", "into", "after", "before", "this", "that", "here", "there", "select", "copy", "cut", "paste", "all", "everything", "text", "sab", "pura", "kuch", "what", "which", "where", "why", "how"}:
            continue
        if token == "+" and "+" not in tokens[index + 1:]:
            continue
        normalized_token = _normalize_key_token(token)
        if normalized_token in {"", "plus"}:
            continue
        if normalized_token in explicit or re.fullmatch(r"[a-z0-9]", normalized_token) or re.fullmatch(r"f\d{1,2}", normalized_token) or len(normalized_token) == 1:
            keys.append(normalized_token)
    return keys


def execute_shortcut(keys):
    key_list = [str(key).lower() for key in (keys or []) if str(key).strip()]
    if not key_list:
        return {"success": False, "message": "no keys provided"}
    if pyautogui is None:
        return {"success": False, "message": "pyautogui is not available in current display environment"}

    normalized_keys = [_normalize_key_token(key) for key in key_list]
    if "fn" in normalized_keys:
        return {
            "success": False,
            "message": "Fn is controlled by the laptop keyboard firmware and cannot be pressed by pyautogui.",
        }

    modifiers = []
    final_key = None
    for key in key_list:
        normalized_key = _normalize_key_token(key)
        if normalized_key in {"ctrl", "shift", "alt", "win"}:
            modifiers.append(normalized_key)
        else:
            final_key = normalized_key

    if final_key is None:
        final_key = key_list[-1]

    if len(key_list) == 1:
        pyautogui.press(str(final_key).lower())
    else:
        pyautogui.hotkey(*normalized_keys)
    return {"success": True, "message": "shortcut executed"}
