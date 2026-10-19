import ctypes
from difflib import SequenceMatcher
import os
import re
import time
from dataclasses import dataclass, field

from brain.phonetic_matcher import choose_confident_candidate, normalize_text, phonetic_similarity, score_candidate

try:
    from pywinauto import Desktop
except ImportError:
    Desktop = None


_OCR_DATA_CACHE = {}


@dataclass
class UIElement:
    name: str
    control_type: str
    automation_id: str
    rectangle: tuple
    enabled: bool
    visible: bool
    patterns: tuple = field(default_factory=tuple)
    wrapper: object = field(default=None, repr=False)


@dataclass
class ScreenClickTarget:
    x: int
    y: int

    def click_input(self, button="left", **_kwargs):
        import pyautogui
        pyautogui.moveTo(self.x, self.y, duration=0.05)
        if button == "right":
            pyautogui.rightClick(self.x, self.y)
        else:
            pyautogui.click(self.x, self.y)


def _describe_click_target(element):
    return {
        "target": getattr(element, "name", "unknown"),
        "match_method": getattr(element, "control_type", "unknown"),
        "bounding_box": getattr(element, "rectangle", None),
    }


def _normalize_match_text(value):
    value = normalize_text(value)
    tokens = {
        "u": "you",
        "ur": "your",
        "pls": "please",
        "thx": "thanks",
        "thanx": "thanks",
    }
    return " ".join(tokens.get(token, token) for token in value.split())


def _match_similarity(wanted, candidate):
    wanted = _normalize_match_text(wanted)
    candidate = _normalize_match_text(candidate)
    if not wanted or not candidate:
        return 0.0
    whole_score = SequenceMatcher(None, wanted, candidate).ratio()
    wanted_tokens = wanted.split()
    candidate_tokens = candidate.split()
    token_score = sum(
        max(SequenceMatcher(None, token, option).ratio() for option in candidate_tokens)
        for token in wanted_tokens
    ) / len(wanted_tokens)
    return max(whole_score, token_score)


def _phonetic_element_match(target, elements, role="", context=None):
    scored = []
    for element in elements:
        if not element.visible or not element.enabled or role and element.control_type.lower() != role.lower():
            continue
        scored.append((score_candidate(target, element.name, context=context, uia=True), element))
    selected = choose_confident_candidate([item[0] for item in scored], minimum_confidence=0.65)
    if selected is None:
        return None
    if selected.phonetic_score < 0.80:
        return None
    for score, element in scored:
        if score is selected:
            print(
                f"[CANDIDATE] text={score.candidate!r} text_score={score.text_score:.2f} "
                f"phonetic_score={score.phonetic_score:.2f} context_score={score.context_score:.2f} "
                f"final={score.final_score:.2f}"
            )
            return element
    return None


def _configure_tesseract(pytesseract):
    configured_command = os.environ.get("MARUTI_TESSERACT_CMD", "")
    known_command = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    current_command = getattr(pytesseract.pytesseract, "tesseract_cmd", "")
    if configured_command and os.path.isfile(configured_command):
        pytesseract.pytesseract.tesseract_cmd = configured_command
    elif not os.path.isfile(current_command) and os.path.isfile(known_command):
        pytesseract.pytesseract.tesseract_cmd = known_command


def _ocr_find_target(target):
    try:
        import pyautogui
        import pytesseract
        _configure_tesseract(pytesseract)
        image = pyautogui.screenshot()
        return _ocr_find_target_in_image(target, image, pytesseract)
    except Exception:
        return None


def _ocr_find_target_in_image(target, image, pytesseract):
    try:
        cache_key = id(image)
        cached = _OCR_DATA_CACHE.get(cache_key)
        if cached is not None and cached[0] is image:
            data = cached[1]
        else:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            _OCR_DATA_CACHE[cache_key] = (image, data)
            while len(_OCR_DATA_CACHE) > 8:
                _OCR_DATA_CACHE.pop(next(iter(_OCR_DATA_CACHE)))
        wanted = _normalize_match_text(target)
        words = []
        for index, value in enumerate(data.get("text", [])):
            text = _normalize_match_text(value)
            if not text:
                continue
            try:
                confidence = float(data.get("conf", [0])[index])
            except (TypeError, ValueError, IndexError):
                confidence = 0.0
            if confidence < 35:
                continue
            left = int(data["left"][index])
            top = int(data["top"][index])
            width = int(data["width"][index])
            height = int(data["height"][index])
            words.append({
                "text": text,
                "left": left,
                "top": top,
                "right": left + width,
                "bottom": top + height,
                "confidence": confidence,
            })
        if words:
            print(f"[OCR] extracted={len(words)} candidates={[item['text'] for item in words]!r}")

        # OCR returns one box per word. Build same-line phrases before matching.
        lines = []
        for word in sorted(words, key=lambda item: (item["top"], item["left"])):
            matching_line = next(
                (
                    line for line in lines
                    if min(word["bottom"], line[0]["bottom"]) - max(word["top"], line[0]["top"]) > 0
                ),
                None,
            )
            if matching_line is None:
                lines.append([word])
            else:
                matching_line.append(word)
        candidates = []
        for line_words in lines:
            line_words.sort(key=lambda item: item["left"])
            for start in range(len(line_words)):
                phrase = []
                for end in range(start, len(line_words)):
                    if phrase:
                        previous = phrase[-1]
                        current = line_words[end]
                        gap = current["left"] - previous["right"]
                        max_gap = max(previous["bottom"] - previous["top"], current["bottom"] - current["top"]) * 3
                        if gap > max_gap:
                            break
                    phrase.append(line_words[end])
                    candidate = " ".join(item["text"] for item in phrase)
                    if candidate == wanted or (len(phrase) == 1 and wanted in candidate):
                        candidates.append((candidate == wanted, sum(item["confidence"] for item in phrase) / len(phrase), phrase))

        exact = [item for item in candidates if item[0]]
        matches = exact or candidates
        if not matches:
            fuzzy = []
            for line_words in lines:
                line_words.sort(key=lambda item: item["left"])
                for start in range(len(line_words)):
                    phrase = []
                    for end in range(start, len(line_words)):
                        if phrase:
                            previous = phrase[-1]
                            current = line_words[end]
                            gap = current["left"] - previous["right"]
                            max_gap = max(previous["bottom"] - previous["top"], current["bottom"] - current["top"]) * 3
                            if gap > max_gap:
                                break
                        phrase.append(line_words[end])
                        candidate = " ".join(item["text"] for item in phrase)
                        score = score_candidate(target, candidate)
                        if score.final_score >= 0.60 and score.phonetic_score >= 0.80:
                            fuzzy.append((score, phrase))
            fuzzy.sort(key=lambda item: item[0].final_score, reverse=True)
            if fuzzy and (len(fuzzy) == 1 or fuzzy[0][0].final_score - fuzzy[1][0].final_score >= 0.08):
                phrase = fuzzy[0][1]
                return (
                    min(item["left"] for item in phrase),
                    min(item["top"] for item in phrase),
                    max(item["right"] for item in phrase),
                    max(item["bottom"] for item in phrase),
                )
            return None
        best_score = max((item[1] for item in matches), default=0.0)
        best = [item for item in matches if item[1] >= best_score - 5]
        if len(best) != 1:
            return None
        phrase = best[0][2]
        left = min(item["left"] for item in phrase)
        top = min(item["top"] for item in phrase)
        right = max(item["right"] for item in phrase)
        bottom = max(item["bottom"] for item in phrase)
        return left, top, right, bottom
    except Exception:
        return None
    return None


def _ui_element_from_control(control):
    info = control.element_info
    rectangle = info.rectangle
    return UIElement(
        info.name or "", info.control_type or "", info.automation_id or "",
        (rectangle.left, rectangle.top, rectangle.right, rectangle.bottom),
        bool(control.is_enabled()), bool(control.is_visible()),
        tuple(name for name in ("invoke", "select", "toggle", "value", "scroll", "click_input") if callable(getattr(control, name, None))),
        control,
    )


def get_active_ui_elements(target=None):
    if Desktop is None:
        return "", []
    try:
        handle = ctypes.windll.user32.GetForegroundWindow()
        if not handle:
            return "", []
        window = Desktop(backend="uia").window(handle=handle)
        if target:
            # A title-filtered UIA query avoids walking a large browser tree before OCR.
            try:
                controls = window.descendants(title=str(target))
            except Exception:
                controls = []
            elements = []
            for control in controls:
                try:
                    elements.append(_ui_element_from_control(control))
                except Exception:
                    continue
            return window.window_text(), elements

        elements = []
        for control in [window, *window.descendants()]:
            try:
                elements.append(_ui_element_from_control(control))
            except Exception:
                continue
        return window.window_text(), elements
    except Exception:
        return "", []


def _visual_find_target(target, visual_candidates):
    wanted = _normalize_match_text(target)
    matches = []
    for candidate in visual_candidates or []:
        if not isinstance(candidate, dict):
            continue
        label = candidate.get("text") or candidate.get("name") or candidate.get("label") or candidate.get("description")
        if not label:
            continue
        normalized = _normalize_match_text(label)
        exact = normalized == wanted
        partial = wanted in normalized or normalized in wanted
        if not exact and not partial:
            continue
        confidence = float(candidate.get("confidence", 0.0) or 0.0)
        rectangle = candidate.get("rectangle") or candidate.get("bbox")
        if isinstance(rectangle, dict):
            left = rectangle.get("left", rectangle.get("x"))
            top = rectangle.get("top", rectangle.get("y"))
            right = rectangle.get("right", (left + rectangle.get("width", 0)) if left is not None else None)
            bottom = rectangle.get("bottom", (top + rectangle.get("height", 0)) if top is not None else None)
            rectangle = (left, top, right, bottom)
        if not rectangle or len(rectangle) != 4 or not all(isinstance(value, (int, float)) for value in rectangle):
            continue
        score = (1.0 if exact else 0.7) * max(confidence, 0.7)
        matches.append((score, tuple(rectangle), label))
    if not matches:
        return None
    matches.sort(reverse=True, key=lambda item: item[0])
    if len(matches) > 1 and matches[0][0] - matches[1][0] < 0.15:
        return None
    _, rectangle, label = matches[0]
    left, top, right, bottom = rectangle
    return UIElement(label, "Visual", "", rectangle, True, True, wrapper=ScreenClickTarget((left + right) // 2, (top + bottom) // 2))


def find_element(target, elements=None, role="", screenshot=None, visual_candidates=None, context=None):
    started = time.perf_counter()
    raw_target = target
    target = _normalize_match_text(target)
    if elements is None:
        _, elements = get_active_ui_elements()
    matches = []
    for element in elements:
        if not element.visible or not element.enabled or role and element.control_type.lower() != role.lower():
            continue
        if _normalize_match_text(element.name) == target:
            matches.append(element)
    if matches:
        result = matches[0] if len(matches) == 1 else None
        if result is not None:
            homophones = [
                element for element in elements
                if element is not result and element.visible and element.enabled
                and phonetic_similarity(raw_target, element.name) >= 0.98
            ]
            if homophones:
                result = None
                print(f"[CLICK] AMBIGUOUS -> NO ACTION target={raw_target!r}")
        print(f"[PERF] target_resolution={(time.perf_counter() - started) * 1000:.1f}ms method=uia_exact")
        return result

    partial_matches = []
    for element in elements:
        name = _normalize_match_text(element.name)
        if not element.visible or not element.enabled or role and element.control_type.lower() != role.lower():
            continue
        if re.search(rf"\b{re.escape(target)}\b", name) and (element.control_type.lower() in {"button", "hyperlink", "menuitem", "tab", "checkbox", "text"} or "click_input" in element.patterns or "invoke" in element.patterns):
            partial_matches.append(element)
    clickable_matches = [element for element in partial_matches if element.control_type.lower() != "text" or "click_input" in element.patterns or "invoke" in element.patterns]
    if len(clickable_matches) == 1:
        print(f"[PERF] target_resolution={(time.perf_counter() - started) * 1000:.1f}ms method=uia_partial")
        return clickable_matches[0]
    if len(partial_matches) == 1:
        print(f"[PERF] target_resolution={(time.perf_counter() - started) * 1000:.1f}ms method=uia_partial")
        return partial_matches[0]

    phonetic_match = _phonetic_element_match(raw_target, elements, role, context=context)
    if phonetic_match is not None:
        print(f"[PERF] target_resolution={(time.perf_counter() - started) * 1000:.1f}ms method=uia_phonetic")
        return phonetic_match

    fuzzy_matches = []
    for element in elements:
        if not element.visible or not element.enabled or role and element.control_type.lower() != role.lower():
            continue
        name = _normalize_match_text(element.name)
        score = _match_similarity(target, name)
        if score >= 0.82:
            fuzzy_matches.append((score, element))
    fuzzy_matches.sort(key=lambda item: item[0], reverse=True)
    if fuzzy_matches and (len(fuzzy_matches) == 1 or fuzzy_matches[0][0] - fuzzy_matches[1][0] >= 0.08):
        print(f"[PERF] target_resolution={(time.perf_counter() - started) * 1000:.1f}ms method=uia_fuzzy")
        return fuzzy_matches[0][1]

    aliases = {
        "cross": ("close", "close button", "x"),
        "x": ("close", "close button", "cross", "x"),
        "three dots": ("...", "more", "more options", "menu"),
        "selected one": ("selected",),
    }
    for alias in aliases.get(target, ()):
        alias_matches = [element for element in elements if " ".join(element.name.lower().split()) == alias and element.visible and element.enabled]
        if len(alias_matches) == 1:
            print(f"[PERF] target_resolution={(time.perf_counter() - started) * 1000:.1f}ms method=uia_alias")
            return alias_matches[0]

    visual_target = _visual_find_target(target, visual_candidates)
    if visual_target:
        print(f"[PERF] target_resolution={(time.perf_counter() - started) * 1000:.1f}ms method=visual")
        return visual_target

    if screenshot is not None:
        try:
            import pytesseract
            _configure_tesseract(pytesseract)
            ocr_target = _ocr_find_target_in_image(target, screenshot, pytesseract)
        except Exception:
            ocr_target = None
    else:
        ocr_target = _ocr_find_target(target)
    if ocr_target:
        if len(ocr_target) == 4:
            left, top, right, bottom = ocr_target
            center = ((left + right) // 2, (top + bottom) // 2)
            rectangle = (left, top, right, bottom)
        else:
            center = tuple(ocr_target)
            rectangle = (*center, *center)
        print(f"[PERF] ocr={(time.perf_counter() - started) * 1000:.1f}ms")
        return UIElement(target, "OCR", "", rectangle, True, True, wrapper=ScreenClickTarget(*center))
    print(f"[PERF] target_resolution={(time.perf_counter() - started) * 1000:.1f}ms method=miss")
    return None


def invoke(element, action):
    if not getattr(element, "visible", True) or not getattr(element, "enabled", True):
        return False
    wrapper = element.wrapper
    if action == "select" and callable(getattr(wrapper, "select", None)):
        try:
            wrapper.select()
            return True
        except Exception:
            return False
    if action == "click":
        info = _describe_click_target(element)
        print(f"TARGET: {info['target']}")
        print(f"MATCH METHOD: {info['match_method']}")
        print(f"BOUNDING BOX: {info['bounding_box']}")
        if isinstance(wrapper, ScreenClickTarget):
            print(f"CLICK POINT: {wrapper.x},{wrapper.y}")
        else:
            print("CLICK POINT: UIA click_input")
        print("DRY RUN: False")
        print(f"CLICK FUNCTION: {type(wrapper).__name__}.click_input/invoke")
        try:
            if callable(getattr(wrapper, "invoke", None)):
                wrapper.invoke()
                print("CLICK EXECUTED: True")
                return True
        except Exception as error:
            print(f"CLICK FUNCTION FAILED: invoke: {type(error).__name__}: {error}")
            if type(error).__name__ == "NoPatternInterfaceError":
                return _physical_click(element)
        try:
            if callable(getattr(wrapper, "click_input", None)):
                wrapper.click_input()
                print("CLICK EXECUTED: True")
                return True
        except Exception as error:
            print(f"CLICK FUNCTION FAILED: click_input: {type(error).__name__}: {error}")
        rectangle = getattr(element, "rectangle", None)
        if isinstance(rectangle, (tuple, list)) and len(rectangle) == 4:
            left, top, right, bottom = rectangle
            if all(isinstance(value, (int, float)) for value in rectangle) and right > left and bottom > top:
                try:
                    return _physical_click(element)
                except Exception as error:
                    print(f"CLICK FUNCTION FAILED: physical fallback: {type(error).__name__}: {error}")
        return False
    if action == "double_click":
        try:
            wrapper.double_click_input()
            return True
        except Exception:
            return False
    if action == "right_click":
        try:
            wrapper.click_input(button="right")
            return True
        except Exception:
            return False
    return False


def _physical_click(element):
    rectangle = getattr(element, "rectangle", None)
    if not isinstance(rectangle, (tuple, list)) or len(rectangle) != 4:
        return False
    left, top, right, bottom = rectangle
    if not all(isinstance(value, (int, float)) for value in rectangle) or right <= left or bottom <= top:
        return False
    try:
        import pyautogui
        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        print(f"PHYSICAL FALLBACK: moveTo({center_x},{center_y}) button=left")
        pyautogui.moveTo(center_x, center_y, duration=0.05)
        pyautogui.click(button="left")
        print("CLICK EXECUTED: True")
        return True
    except Exception as error:
        print(f"CLICK FUNCTION FAILED: physical fallback: {type(error).__name__}: {error}")
        return False
