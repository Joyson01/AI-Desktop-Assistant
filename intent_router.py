"""Intent router: English / Hindi / Hinglish text -> Intent(name, args, confidence).

Rule-based on purpose (fast, offline, testable). Supports desktop automation:
- Application, URL, and folder launching
- System volume control (absolute percentages, relative steps, mute/unmute)
- Bounded scrolling (with qualifiers 'little', 'lot' and repetition counts)
- Browser and video targeting ('click the first video')
- Screen perception & OCR ('what is on my screen', 'read visible text')
- Safe confirmation gates for sensitive actions
- Fallback to Gemini conversation brain ('chat')
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from core.context import ConversationContext
import registry


@dataclass
class Intent:
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    raw: str = ""
    is_ambiguous: bool = False
    clarification_prompt: Optional[str] = None


NAMES = r"(?:maruti|maruthi|maruty|marooti|maurti|moruti|marute)"
WAKE_RE = re.compile(rf"\b{NAMES}\b", re.I)
WAKE_START_RE = re.compile(rf"^\s*(?:(?:hello|hey|hi|ok|okay)\s+)?{NAMES}\b[\s,.:-]*", re.I)

HINDI_MAP = {
    "खोलो": "open", "खोल": "open", "खोलिए": "open", "बंद": "close",
    "लिखो": "type", "लिख": "type", "लिखिए": "type",
    "खोजो": "search", "ढूंढो": "search", "ढूंढ": "search", "खोज": "search",
    "क्रोम": "chrome", "नोटपैड": "notepad", "कैलकुलेटर": "calculator", "यूट्यूब": "youtube",
    "ब्राउज़र": "browser", "ब्राउजर": "browser", "टेक्स्ट": "text", "एडिटर": "editor",
    "दस्तावेज़": "document", "कॉपी": "copy", "पेस्ट": "paste", "काटो": "cut",
    "आवाज़": "volume", "आवाज": "volume", "कम": "low", "बढ़ाओ": "increase",
    "पहला": "first", "पहली": "first", "दूसरा": "second", "तीसरा": "third",
    "चौथा": "fourth", "पांचवा": "fifth", "म्यूट": "mute",
    "रुको": "pause", "रोक": "pause", "चलाओ": "play", "बजाओ": "play",
}

VERB_MAP = [
    (r"\b(?:kholo|khol|kholiye|chalu|shuru)\b", "open"),
    (r"\b(?:band|bandh)\b", "close"),
    (r"\b(?:likho|likh|likhiye)\b", "type"),
    (r"\b(?:dhundo|dhoondo|khojo|khoj)\b", "search"),
    (r"\b(?:bajao|chalao|lagao)\b", "play"),
    (r"\b(?:awaaz|aawaz|dhwani)\b", "volume"),
    (r"\b(?:kam|ghatao|dheeme|dheere)\b", "low"),
    (r"\b(?:badhao|badha|tez)\b", "increase"),
    (r"\b(?:thoda|thodi|zara)\b", "little"),
    (r"\b(?:bahut|jyada)\b", "lot"),
    (r"\b(?:pehla|pehli)\b", "first"),
    (r"\b(?:doosra|doosri|dusra|dusri)\b", "second"),
    (r"\b(?:teesra|teesri|tisra|tisri)\b", "third"),
    (r"\b(?:chautha|chauthi)\b", "fourth"),
    (r"\b(?:panchwa|panchwi)\b", "fifth"),
    (r"\b(?:rok\s+do|rok\s+de|rok\s+lo|ruko|rok|ruk)\b", "pause"),
    (r"\b(?:baar|bar)\b", "times"),
    (r"\b(?:pratishat|pratishath|taka)\b", "percent"),
    (r"\bneeche\b", "down"),
    (r"\b(?:upar|oopar)\b", "up"),
    (r"\baage\b", "forward"),
    (r"\b(?:peeche|piche)\b", "back"),
    (r"\b(?:naya|nayi)\b", "new"),
]

FILLER = r"\b(?:please|plz|karo|kar do|kardo|kijiye|kijiyega|jao|jaao)\b"

KNOWN_FOLDERS = {"downloads", "documents", "desktop", "home", "pictures", "music", "videos"}

KEY_ALIASES = {
    "control": "ctrl", "ctl": "ctrl", "windows": "win", "window": "win", "escape": "esc",
    "return": "enter", "del": "delete",
}
NUM_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "twenty": "20", "fifty": "50", "hundred": "100",
}
MODIFIERS = {"ctrl", "alt", "shift", "win"}
NAMED_KEYS = MODIFIERS | {
    "tab", "enter", "esc", "space", "backspace", "delete", "home", "end", "pageup",
    "pagedown", "up", "down", "left", "right", "capslock",
} | {f"f{i}" for i in range(1, 13)}

SHORTCUTS = {
    "select all": ["ctrl", "a"], "copy": ["ctrl", "c"], "paste": ["ctrl", "v"], "cut": ["ctrl", "x"],
    "undo": ["ctrl", "z"], "redo": ["ctrl", "y"], "save": ["ctrl", "s"], "refresh": ["f5"],
}


def normalize(text: str) -> str:
    # 1. Unicode normalization (NFKC)
    t = unicodedata.normalize("NFKC", text).strip()
    for dev, en in HINDI_MAP.items():
        t = t.replace(dev, f" {en} ")
    t = re.sub(r"\s+dot\s+", ".", t, flags=re.I)
    t = re.sub(r"[?!,;:]+", " ", t).strip(" .")
    for pat, rep in VERB_MAP:
        t = re.sub(pat, rep, t, flags=re.I)
    t = re.sub(FILLER, " ", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def parse_keys(spec: str):
    s = re.sub(r"\bplus\b|\+", " ", spec.lower())
    s = s.replace("page up", "pageup").replace("page down", "pagedown").replace("caps lock", "capslock")
    s = re.sub(r"\s+arrow(?:s)?\b", "", s)
    s = re.sub(r"\barrow\s+key\s+", "", s)
    out = []
    for tok in s.split():
        tok = NUM_WORDS.get(KEY_ALIASES.get(tok, tok), KEY_ALIASES.get(tok, tok))
        if tok in NAMED_KEYS or len(tok) == 1:
            out.append(tok)
        else:
            return None
    if not out or len([k for k in out if k not in MODIFIERS]) > 1:
        return None
    return out


ORDINALS = {
    "first": 1, "1st": 1, "one": 1, "1": 1, "pehla": 1, "pehli": 1,
    "second": 2, "2nd": 2, "two": 2, "2": 2, "doosra": 2, "dusra": 2, "doosri": 2, "dusri": 2,
    "third": 3, "3rd": 3, "three": 3, "3": 3, "teesra": 3, "tisra": 3, "teesri": 3, "tisri": 3,
    "fourth": 4, "4th": 4, "four": 4, "4": 4, "chautha": 4, "chauthi": 4,
    "fifth": 5, "5th": 5, "five": 5, "5": 5, "panchwa": 5, "panchwi": 5,
}

LINE_NUMS = {
    "one": 1, "1": 1, "first": 1, "1st": 1, "pehli": 1, "pehla": 1,
    "two": 2, "2": 2, "second": 2, "2nd": 2, "doosri": 2, "doosra": 2,
    "three": 3, "3": 3, "third": 3, "3rd": 3, "teesri": 3, "teesra": 3,
    "four": 4, "4": 4, "fourth": 4, "4th": 4, "chauthi": 4, "chautha": 4,
    "five": 5, "5": 5, "fifth": 5, "5th": 5, "panchwi": 5, "panchwa": 5,
    "six": 6, "6": 6, "sixth": 6, "6th": 6,
    "seven": 7, "7": 7, "seventh": 7, "7th": 7,
    "eight": 8, "8": 8, "eighth": 8, "8th": 8,
    "nine": 9, "9": 9, "ninth": 9, "9th": 9,
    "ten": 10, "10": 10, "tenth": 10, "10th": 10,
}


def _match(t: str, context: Optional[ConversationContext] = None):
    def fm(p):
        return re.fullmatch(p, t, re.I)

    # 1. Greetings
    if fm(r"(?:hello|hi|hey|namaste|namaskar)(?: there)?"):
        return Intent("greet")

    # 2. Exit phrases — check before generic patterns
    if fm(r"(?:exit|quit|bye|goodbye|stop listening|good night)"
           r"|(?:exit|quit|stop)\s+(?:assistant|maruti|program|app|application)"
           r"|(?:stop|close)\s+(?:the\s+)?assistant"):
        return Intent("exit")

    # 3. Media Controls (Pause / Resume)
    if fm(r"pause(?: (?:the )?(?:video|music|playback|song|media))?") or fm(r"(?:video|music|song) pause") or fm(r"pause"):
        return Intent("media_pause")
    if (
        fm(r"(?:resume|unpause)(?: (?:the )?(?:video|music|playback|song|media))?")
        or fm(r"(?:video|music|song) resume")
        or fm(r"resume")
        or fm(r"open")
        or (fm(r"play") and (context and (context.is_youtube_active() or context.page_state in ("watch", "paused"))))
    ):
        return Intent("media_resume")

    # 4. System Volume Control (Phase 5)
    # Mute / Unmute
    if fm(r"mute(?: audio| volume)?") or fm(r"volume mute") or fm(r"audio mute") or fm(r"volume (?:close|band|off)"):
        return Intent("volume_mute", {"state": True})
    if fm(r"unmute(?: audio| volume)?") or fm(r"volume unmute") or fm(r"audio unmute") or fm(r"volume (?:open|chalu|on)"):
        return Intent("volume_mute", {"state": False})

    # Absolute Volume setting
    if fm(r"(?:set )?volume (?:to )?(?:zero|0)") or fm(r"volume zero"):
        return Intent("volume_set", {"percent": 0.0})
    if fm(r"(?:set )?volume (?:to )?(?:maximum|max|full|100)") or fm(r"full volume"):
        return Intent("volume_set", {"percent": 100.0})
    if m := (fm(r"(?:set )?volume (?:to )?(\d+)(?: percent|%)?") or fm(r"volume (\d+)(?: percent|%)?")):
        return Intent("volume_set", {"percent": float(m.group(1))})

    # Relative Volume adjustments
    if m := (fm(r"(?:increase|raise|turn up)(?: the)? volume by (\d+)(?: percent|%)?") or fm(r"volume (\d+)(?: percent|%)? increase")):
        return Intent("volume_change", {"delta": float(m.group(1))})
    if m := (fm(r"(?:lower|decrease|reduce|turn down)(?: the)? volume by (\d+)(?: percent|%)?") or fm(r"volume (\d+)(?: percent|%)? low")):
        return Intent("volume_change", {"delta": -float(m.group(1))})
    if fm(r"(?:increase|raise|turn up)(?: the)? volume") or fm(r"volume (?:up|high|increase)"):
        return Intent("volume_change", {"delta": 15.0})
    if fm(r"(?:lower|decrease|reduce|turn down)(?: the)? volume") or fm(r"volume (?:low|down)"):
        return Intent("volume_change", {"delta": -15.0})

    # 5. Perception & Screen Understanding (Phase 7)
    if fm(r"what is on (?:my |the )?screen") or fm(r"what'?s on (?:my |the )?screen") or fm(r"screen (?:pe|par) kya hai") or fm(r"inspect screen"):
        return Intent("inspect_screen")
    if fm(r"read (?:the )?(?:visible )?text") or fm(r"read (?:the )?screen") or fm(r"screen (?:ka )?text padho") or fm(r"visible text padho"):
        return Intent("read_screen")

    # 6. Browser Video & Link targeting (Phase 6)
    if m := (
        fm(r"(?:click|play|open)(?: the| on)? (first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|\d+)(?:st|nd|rd|th)? video(?: on youtube)?")
        or fm(r"(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|\d+)(?:st|nd|rd|th)? video (?:play|open|click)")
        or fm(r"find (?:the )?(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|\d+)(?:st|nd|rd|th)? video")
        or fm(r"(?:click|play|open)(?: the| on)? video (\d+)")
    ):
        ord_key = m.group(1).lower()
        idx = ORDINALS.get(ord_key)
        if not idx and ord_key.isdigit():
            idx = int(ord_key)
        return Intent("browser_click_video", {"index": idx or 1})

    if fm(r"(?:click|play|open)(?: the| on)? first video(?: on youtube)?") or fm(r"first video (?:play|open)") or fm(r"find (?:the )?first video"):
        return Intent("browser_click_video", {"index": 1})
    if m := fm(r"find (?:the )?link (?:that says |labeled |named )?(.+)"):
        return Intent("click", {"label": m.group(1)})
    if m := fm(r"click (?:the )?button (?:labeled |named |called )?(.+)"):
        return Intent("click", {"label": m.group(1)})

    # 7. Folder Launching (Phase 3)
    if m := (fm(r"(?:open|launch) (downloads|documents|desktop|home|pictures|music|videos)(?: folder)?") or fm(r"(downloads|documents|desktop|home|pictures|music|videos) folder open")):
        return Intent("open_folder", {"folder": m.group(1).lower()})

    # 8. Text Editing, Selection & Clipboard Automation
    # 8a. Hello World
    if re.search(r"hello world", t, re.I) and re.search(r"\b(?:code|program|script)\b", t, re.I):
        return Intent("hello_world")

    # 8b. Key Presses & Newlines
    if fm(r"insert (?:a )?new line|new line"):
        return Intent("press_keys", {"keys": ["enter"]})
    if fm(r"(?:press|hit) enter"):
        return Intent("press_keys", {"keys": ["enter"]})
    if fm(r"(?:press|hit) tab"):
        return Intent("press_keys", {"keys": ["tab"]})
    if fm(r"(?:press|hit) space"):
        return Intent("press_keys", {"keys": ["space"]})
    if fm(r"(?:press|hit)? ?backspace"):
        return Intent("press_keys", {"keys": ["backspace"]})
    if fm(r"(?:press|hit)? ?delete"):
        return Intent("press_keys", {"keys": ["delete"]})
    if m := fm(r"(?:(?:press|hit)\s+)?(left|right|up|down)\s+arrow|(?:press|hit)\s+(left|right|up|down)"):
        k = (m.group(1) or m.group(2)).lower()
        return Intent("press_keys", {"keys": [k]})
    if fm(r"delete selected(?: text)?|delete selection"):
        return Intent("delete_selected")

    # 8c. Selection Commands
    if fm(r"select all text|select everything"):
        return Intent("select_all")
    if fm(r"select all"):
        return Intent("press_keys", {"keys": ["ctrl", "a"]})

    if m := (
        fm(r"select line (one|two|three|four|five|six|seven|eight|nine|ten|\d+)")
        or fm(r"select line number (\d+)")
        or fm(r"select (?:the )?(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|4th|5th) line")
    ):
        raw_num = m.group(1).lower()
        line_num = LINE_NUMS.get(raw_num) or (int(raw_num) if raw_num.isdigit() else None)
        return Intent("select_line", {"line_number": line_num})

    if fm(r"select (?:the )?(?:current )?line|select this line"):
        return Intent("select_line", {"line_number": None})

    if fm(r"select (?:the )?(?:current )?word|select this word"):
        return Intent("select_word", {"direction": "current"})
    if fm(r"select (?:the )?next word"):
        return Intent("select_word", {"direction": "next"})
    if fm(r"select (?:the )?(?:previous|prev) word"):
        return Intent("select_word", {"direction": "previous"})

    if fm(r"select (?:from (?:the )?cursor )?to (?:the )?(?:beginning|start) of (?:the )?line"):
        return Intent("select_to_boundary", {"boundary": "line_start"})
    if fm(r"select (?:from (?:the )?cursor )?to (?:the )?end of (?:the )?line"):
        return Intent("select_to_boundary", {"boundary": "line_end"})
    if fm(r"select (?:from (?:the )?cursor )?to (?:the )?(?:beginning|start) of (?:the )?document"):
        return Intent("select_to_boundary", {"boundary": "doc_start"})
    if fm(r"select (?:from (?:the )?cursor )?to (?:the )?end of (?:the )?document"):
        return Intent("select_to_boundary", {"boundary": "doc_end"})
    if fm(r"clear selection|clear the selection|deselect(?: all)?"):
        return Intent("clear_selection")

    # 8d. Cursor Navigation
    if fm(r"(?:go|move)(?: cursor)? to (?:the )?(?:beginning|start|top) of (?:the )?document"):
        return Intent("go_to_boundary", {"boundary": "doc_start"})
    if fm(r"(?:go|move)(?: cursor)? to (?:the )?(?:end|bottom) of (?:the )?document"):
        return Intent("go_to_boundary", {"boundary": "doc_end"})
    if fm(r"(?:go|move)(?: cursor)? to (?:the )?(?:beginning|start) of (?:the )?line"):
        return Intent("go_to_boundary", {"boundary": "line_start"})
    if fm(r"(?:go|move)(?: cursor)? to (?:the )?end of (?:the )?line"):
        return Intent("go_to_boundary", {"boundary": "line_end"})

    if m := fm(r"move (?:the )?cursor (left|right|up|down)(?: (\d+|one|two|three|four|five) (?:steps?|times?))?"):
        d = m.group(1).lower()
        st_raw = m.group(2)
        steps = 1
        if st_raw:
            steps = LINE_NUMS.get(st_raw.lower()) or (int(st_raw) if st_raw.isdigit() else 1)
        return Intent("move_cursor", {"direction": d, "steps": steps})

    # 8e. Clipboard & Editing Actions
    if fm(r"copy(?: that| text| selection)?"):
        return Intent("clipboard_copy")
    if fm(r"cut(?: that| text| selection)?"):
        return Intent("clipboard_cut")
    if fm(r"paste(?: that| text)?"):
        return Intent("clipboard_paste")
    if fm(r"undo(?: that| edit)?"):
        return Intent("edit_undo")
    if fm(r"redo(?: that| edit)?"):
        return Intent("edit_redo")
    if m := fm(r"find text (.+)|find in document (.+)"):
        q = (m.group(1) or m.group(2)).strip()
        return Intent("find_text", {"query": q})
    if fm(r"replace text|find and replace"):
        return Intent("replace_text")
    if fm(r"save as(?: file| document)?|save file as|save document as"):
        return Intent("save_file_as")
    if fm(r"save(?: file| document)?"):
        return Intent("save_file")
    if fm(r"cancel|cancel action"):
        return Intent("cancel")

    # Generic typing and key parsing fallbacks
    if m := fm(r"type (.+)"):
        return Intent("type_text", {"text": m.group(1)})
    if m := fm(r"(?:press|hit|push) (.+)"):
        keys = parse_keys(m.group(1))
        return Intent("press_keys", {"keys": keys}) if keys else Intent("unknown", confidence=0.3)
    if t.lower() in SHORTCUTS:
        return Intent("press_keys", {"keys": SHORTCUTS[t.lower()]})
    if m := fm(r"caps ?(?:lock)?(?: (on|off))?"):
        return Intent("caps", {"state": (m.group(1) or "toggle").lower()})

    # 9. Enhanced Scrolling (Phase 4)
    # Scrolling with qualifiers (little, lot)
    if m := (fm(r"scroll (up|down) a? ?(little|lot)") or fm(r"(little|lot) scroll (up|down)") or fm(r"(little|lot) (up|down) scroll")):
        dir_val = m.group(1) if m.group(1).lower() in ("up", "down") else m.group(2)
        qual_val = m.group(2) if m.group(1).lower() in ("up", "down") else m.group(1)
        step_amount = 200 if qual_val.lower() == "little" else 800
        return Intent("scroll", {"direction": dir_val.lower(), "amount": step_amount, "qualifier": qual_val.lower()})

    # Scrolling with repetitions (e.g. 3 times or scroll down 3)
    if m := (
        fm(r"scroll (up|down) (\d+) times")
        or fm(r"(\d+) times scroll (up|down)")
        or fm(r"(\d+) times (up|down) scroll")
        or fm(r"scroll (up|down) ([1-9]|10)")
        or fm(r"([1-9]|10) (?:times )?scroll (up|down)")
    ):
        dir_val = m.group(1) if m.group(1).lower() in ("up", "down") else m.group(2)
        reps_val = int(m.group(2) if m.group(1).lower() in ("up", "down") else m.group(1))
        return Intent("scroll", {"direction": dir_val.lower(), "amount": 400, "repetitions": reps_val})

    # Scrolling to top / bottom boundaries
    if fm(r"scroll (?:to (?:the )?)?(?:top|beginning)"):
        return Intent("scroll", {"direction": "up", "amount": 2000, "boundary": "top"})
    if fm(r"scroll (?:to (?:the )?)?(?:bottom|end)"):
        return Intent("scroll", {"direction": "down", "amount": 2000, "boundary": "bottom"})

    # Standard scrolling (keeps default 500 for existing backward compatibility)
    if m := fm(r"scroll (up|down)(?: (\d+))?") or fm(r"(up|down) scroll(?: (\d+))?"):
        return Intent("scroll", {"direction": m.group(1).lower(), "amount": int(m.group(2) or 500)})

    # 10. Window and Tab navigation
    if m := fm(r"(?:go )?(forward|back|backward)(?: page)?"):
        return Intent("nav", {"direction": "forward" if m.group(1).lower() == "forward" else "back"})
    if fm(r"(?:open )?(?:a )?new tab(?: open)?"):
        return Intent("new_tab")
    if fm(r"close (?:this |current |the |all )?tabs?"):
        return Intent("close_tab")
    if fm(r"minimi[sz]e(?: (?:the |this )?(?:screen|window))?") or fm(r"(?:the |this )?(?:screen|window) minimi[sz]e"):
        return Intent("minimize")
    if fm(r"close (?:the |this |current )?(?:window|screen)") or fm(r"(?:the |this |current )?(?:window|screen) close"):
        return Intent("close_window")
    if fm(r"switch(?: the)?(?: window| windows| app)?") or fm(r"(?:window|app) switch"):
        return Intent("switch_window")

    # 11. Search and Play intents
    # 11a. Explicit Google search: always overrides current context
    if m := (
        fm(r"(?:search|google)(?: on| using| with)? google (?:for )?(.+)")
        or fm(r"search for (.+?) (?:on|with|using) google")
    ):
        raw_q = m.group(1).strip()
        raw_q = re.sub(r"^(?:google|bing|duckduckgo|web)\s+(?:for\s+)?", "", raw_q, flags=re.I)
        return Intent("web_search", {"query": raw_q.strip()})

    # 11b. Explicit YouTube intents
    if m := (fm(r"(search|play)(?: for)? (.+?) (?:on|in|pe|par) youtube")):
        return Intent("youtube", {"query": m.group(2).strip(), "play": m.group(1).lower() == "play"})
    if m := fm(r"(?:search|play) youtube (?:for |pe |par )?(.+)"):
        return Intent("youtube", {"query": m.group(1).strip(), "play": t.lower().startswith("play")})
    if m := fm(r"youtube (?:on|pe|par) (?:search |play )?(.+?)( search| play)?"):
        return Intent("youtube", {"query": m.group(1).strip(), "play": "play" in (m.group(2) or "")})
    if fm(r"search youtube"):
        return Intent("open", {"kind": "site", "target": "https://www.youtube.com", "label": "youtube"}, 1.0)

    # 11c. Context-Aware YouTube Search: when YouTube is active context
    if context and context.is_youtube_active():
        if m := fm(r"(?:search|find)(?: for)? (.+)"):
            return Intent("youtube", {"query": m.group(1).strip(), "play": False})
        if m := fm(r"(.+) (?:search|find)"):
            return Intent("youtube", {"query": m.group(1).strip(), "play": False})

    # 11d. General Play command
    if m := fm(r"play (.+)") or fm(r"(.+) play"):
        return Intent("youtube", {"query": m.group(1).strip(), "play": True})

    # 11e. Generic Web Search (when YouTube is not active context)
    if m := fm(r"(?:search|google)(?: on| using| with)?(?: google| bing| web)?(?: for)? (.+)"):
        raw_q = m.group(1)
        raw_q = re.sub(r"^(?:google|bing|duckduckgo|web)\s+(?:for\s+)?", "", raw_q, flags=re.I)
        return Intent("web_search", {"query": raw_q.strip()})
    if m := fm(r"(.+) search"):
        return Intent("web_search", {"query": m.group(1).strip()})

    # 12. Weather
    if re.search(r"\b(?:weather|mausam)\b", t, re.I):
        from config import DEFAULT_CITY
        city = None
        if m := re.search(r"\b(?:weather|mausam)\b(?:\s+(?:of|in|at|for))?\s*(.*)$", t, re.I):
            city = re.sub(r"^(?:(?:of|in|at|for|today|now|currently|like)\s+)+", "", m.group(1).strip(), flags=re.I)
        if not city and (m := re.search(r"(\w+)\s+(?:ka|ki)\s+(?:weather|mausam)", t, re.I)):
            city = m.group(1)
        return Intent("weather", {"city": city or DEFAULT_CITY})

    # 13. Visual Click
    if m := fm(r"click(?: on)? (.+)"):
        return Intent("click", {"label": m.group(1)})

    # 14. Application & Website Launch
    if m := fm(r"(?:open|launch|start|run) (.+)") or fm(r"(.+?) (?:open|launch|start)"):
        target_name = m.group(1).strip()
        # Check if it's a known folder
        folder_candidate = target_name.lower().replace("folder", "").strip()
        if folder_candidate in KNOWN_FOLDERS:
            return Intent("open_folder", {"folder": folder_candidate})
        kind, target, conf, label = registry.resolve(target_name)
        if conf < 0.6:
            return Intent("unknown", {"heard": target_name}, conf)
        return Intent("open", {"kind": kind, "target": target, "label": label}, conf)

    return None


class IntentRouter:
    @staticmethod
    def has_wake(text: str) -> bool:
        return bool(WAKE_RE.search(text))

    def route(self, text: str, context: Optional[ConversationContext] = None) -> Intent:
        # 0. Active Dictation Mode check
        if context and getattr(context, "is_dictation_mode", False):
            if text.strip().lower() in ("stop dictation", "end dictation", "exit dictation", "dictation band karo"):
                return Intent("stop_dictation", raw=text)
            # Literal dictation - do not alter text or parse commands
            return Intent("type_text", {"text": text.strip(), "newline": False}, raw=text)

        body = WAKE_START_RE.sub("", text, count=1).strip()

        # Dictation mode explicit start/stop commands
        if re.match(r"^(?:start|enable|begin)\s+dictation(?:\s+mode)?$|^dictation\s+mode$", body, re.I):
            return Intent("start_dictation", raw=text)
        if re.match(r"^(?:stop|end|disable)\s+dictation(?:\s+mode)?$", body, re.I):
            return Intent("stop_dictation", raw=text)

        # 1. Compound open-and-type command (e.g. 'Open Notepad and type hello')
        if m := re.match(
            r"^(?:open|launch|kholo)\s+(?:a\s+)?(notepad|text\s+editor|new\s+document|document|editor)\s+(?:and\s+)?(?:type|write|likho)\s+(.+)$",
            body,
            re.I,
        ):
            text_payload = m.group(2).strip().rstrip(".?!")
            return Intent("open_and_type", {"app": "notepad", "text": text_payload}, raw=text)

        # 2. Multi-line dictation ('Type this on the next line: My name is Joyson.')
        if m := re.match(
            r"^(?:type|write|likho)\s+(?:this\s+)?on\s+the\s+next\s+line\s*[:,-]?\s*(.+)$",
            body,
            re.I,
        ):
            text_payload = m.group(1).strip().rstrip(".?!")
            return Intent("type_text", {"text": text_payload, "newline": True}, raw=text)

        # 3. Direct text dictation / typing commands ('Type hello', 'Write hello world', 'likho namaste')
        if m := re.match(r"^(?:type|write|likho|likh|likhiye)\s+(.+)$", body, re.I):
            # Guard against 'write a simple hello world code'
            if not (re.search(r"hello\s+world", body, re.I) and re.search(r"\b(?:code|program|script)\b", body, re.I)):
                text_payload = m.group(1).strip().rstrip(".?!")
                return Intent("type_text", {"text": text_payload, "newline": False}, raw=text)

        if m := re.match(r"^(.+?)\s+(?:likho|likh|likhiye)$", body, re.I):
            text_payload = m.group(1).strip().rstrip(".?!")
            if text_payload.lower() not in ("kuch", "kuchh"):
                return Intent("type_text", {"text": text_payload, "newline": False}, raw=text)

        # 4. Search and dhoondo commands with literal queries preserved
        if m := re.match(r"^(?:dhoondo|dhundo|khojo|khoj)\s+(.+)$", body, re.I):
            q = m.group(1).strip()
            return Intent("web_search", {"query": q}, raw=text)

        t = normalize(body)
        if not t:
            return Intent("greet" if self.has_wake(text) else "empty", raw=text)
        intent = _match(t, context=context)
        if intent is None:
            intent = Intent("chat", {"question": t})
        intent.raw = text
        return intent
