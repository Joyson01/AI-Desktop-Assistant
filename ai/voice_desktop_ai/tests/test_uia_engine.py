from uia_engine import UIElement, ScreenClickTarget, find_element, invoke


class FakeWrapper:
    def __init__(self):
        self.invoked = False
        self.clicked = False

    def invoke(self):
        self.invoked = True
        raise RuntimeError("invoke failed")

    def click_input(self, **kwargs):
        self.clicked = True


def test_find_element_refuses_duplicate_exact_matches():
    first = UIElement("Open", "Button", "", (0, 0, 10, 10), True, True)
    second = UIElement("Open", "Button", "", (20, 0, 30, 10), True, True)
    assert find_element("Open", [first, second]) is None


def test_find_element_exact_normalized_match_is_used_before_fallbacks(monkeypatch):
    element = UIElement("  Settings  ", "Button", "", (10, 20, 110, 60), True, True)
    monkeypatch.setattr("uia_engine._ocr_find_target", lambda target: (_ for _ in ()).throw(AssertionError("OCR should not run")))

    assert find_element("settings", [element]) is element


def test_find_element_does_not_match_target_inside_another_word(monkeypatch):
    monkeypatch.setattr("uia_engine._ocr_find_target", lambda target: None)
    unrelated = UIElement("Profile", "Text", "", (0, 0, 10, 10), True, True)
    assert find_element("file", [unrelated]) is None


def test_find_element_prefers_clickable_partial_match():
    text = UIElement("Settings panel", "Text", "", (0, 0, 10, 10), True, True)
    button = UIElement("Settings menu", "Button", "", (20, 0, 30, 10), True, True)
    assert find_element("settings", [text, button]) is button


def test_find_element_fuzzy_matches_typo_and_returns_rectangle_center():
    element = UIElement("Settings", "Button", "", (500, 300, 620, 340), True, True)

    result = find_element("setings", [element])

    assert result is element
    assert ((result.rectangle[0] + result.rectangle[2]) // 2, (result.rectangle[1] + result.rectangle[3]) // 2) == (560, 320)


def test_find_element_matches_pronunciation_variant_in_full_visible_sentence():
    element = UIElement(
        "Website Developer @ Bee Online Communication",
        "Hyperlink",
        "",
        (100, 200, 600, 240),
        True,
        True,
    )

    result = find_element("website developar", [element])

    assert result is element


def test_find_element_fuzzy_matches_multiword_ocr_pronunciation(monkeypatch):
    import pyautogui
    import pytesseract

    monkeypatch.setattr(pyautogui, "screenshot", lambda: object())
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda image, output_type: {
            "text": ["Account", "Setings"],
            "left": [100, 190], "top": [200, 200],
            "width": [80, 70], "height": [24, 24],
            "conf": [95, 93],
        },
    )

    element = find_element("Account Settings", [])

    assert element is not None
    assert element.rectangle == (100, 200, 260, 224)


def test_find_element_matches_spoken_u_to_visible_you(monkeypatch):
    element = UIElement("Thank You", "Text", "", (700, 620, 790, 650), True, True)

    result = find_element("thank u", [element])

    assert result is element


def test_screen_click_target_supports_right_click(monkeypatch):
    calls = []
    monkeypatch.setattr("pyautogui.rightClick", lambda x, y: calls.append((x, y)))

    ScreenClickTarget(560, 320).click_input(button="right")

    assert calls == [(560, 320)]


def test_invoke_falls_back_to_click_input_when_invoke_fails():
    wrapper = FakeWrapper()
    element = UIElement("Open", "Button", "", (0, 0, 10, 10), True, True, wrapper=wrapper)
    assert invoke(element, "click") is True
    assert wrapper.invoked is True
    assert wrapper.clicked is True


def test_invoke_uses_rectangle_center_when_uia_click_fails(monkeypatch):
    calls = []

    class BrokenWrapper:
        def invoke(self):
            raise RuntimeError("NoPatternInterfaceError")

        def click_input(self, **kwargs):
            raise RuntimeError("click_input failed")

    monkeypatch.setattr("pyautogui.moveTo", lambda x, y, duration: calls.append(("move", x, y, duration)))
    monkeypatch.setattr("pyautogui.click", lambda **kwargs: calls.append(("click", kwargs)))
    element = UIElement("Settings", "Button", "", (500, 300, 620, 340), True, True, wrapper=BrokenWrapper())

    assert invoke(element, "click") is True
    assert calls == [("move", 560, 320, 0.05), ("click", {"button": "left"})]


def test_find_element_uses_screen_target_when_uia_has_no_match(monkeypatch):
    monkeypatch.setattr("uia_engine._ocr_find_target", lambda target: (120, 240))
    element = find_element("open", [])
    assert element is not None
    assert isinstance(element.wrapper, ScreenClickTarget)
    assert element.wrapper.x == 120
    assert element.wrapper.y == 240


def test_click_target_uses_ocr_when_uia_target_is_unavailable(monkeypatch):
    monkeypatch.setattr("uia_engine._ocr_find_target", lambda target: (300, 400))

    element = find_element("File", [])

    assert element.name == "file"
    assert (element.wrapper.x, element.wrapper.y) == (300, 400)


def test_ocr_resolves_visible_communication_when_uia_has_no_target(monkeypatch):
    import pyautogui
    import pytesseract

    monkeypatch.setattr(pyautogui, "screenshot", lambda: object())
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda image, output_type: {
            "text": ["Features", "Communication", "History"],
            "left": [40, 72, 70], "top": [400, 500, 550],
            "width": [70, 130, 60], "height": [24, 25, 24],
            "conf": [94, 91, 95],
        },
    )

    element = find_element("communication", [])

    assert element is not None
    assert element.rectangle == (72, 500, 202, 525)
    assert (element.wrapper.x, element.wrapper.y) == (137, 512)


def test_ocr_groups_adjacent_words_and_selects_exact_profile(monkeypatch):
    import pyautogui
    import pytesseract

    monkeypatch.setattr(pyautogui, "screenshot", lambda: object())
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda image, output_type: {
            "text": ["Vandana", "Yadav", "Nehru", "Yadav"],
            "left": [320, 390, 560, 630],
            "top": [520, 520, 520, 520],
            "width": [60, 50, 45, 50],
            "height": [20, 20, 20, 20],
            "conf": [95, 95, 96, 96],
        },
    )

    element = find_element("Nehru Yadav", [])

    assert element.rectangle == (560, 520, 680, 540)
    assert (element.wrapper.x, element.wrapper.y) == (620, 530)


def test_ocr_does_not_match_words_across_a_wide_screen_gap(monkeypatch):
    import pyautogui
    import pytesseract

    monkeypatch.setattr(pyautogui, "screenshot", lambda: object())
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda image, output_type: {
            "text": ["Nehru", "unrelated", "Yadav"],
            "left": [100, 300, 900],
            "top": [520, 520, 520],
            "width": [50, 80, 50],
            "height": [20, 20, 20],
            "conf": [95, 95, 95],
        },
    )

    assert find_element("Nehru Yadav", []) is None


def test_ocr_refuses_equal_partial_matches(monkeypatch):
    import pyautogui
    import pytesseract

    monkeypatch.setattr(pyautogui, "screenshot", lambda: object())
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda image, output_type: {
            "text": ["Nehru", "Nehru"],
            "left": [320, 560],
            "top": [520, 520],
            "width": [45, 45],
            "height": [20, 20],
            "conf": [95, 95],
        },
    )

    assert find_element("Nehru", []) is None


def test_visual_candidate_resolves_non_text_icon_without_coordinates_in_command():
    element = find_element(
        "three dots",
        [],
        visual_candidates=[
            {"label": "three dots", "bbox": {"left": 700, "top": 40, "right": 724, "bottom": 64}, "confidence": 0.94},
        ],
    )

    assert (element.wrapper.x, element.wrapper.y) == (712, 52)


def test_visual_candidates_refuse_close_scores():
    element = find_element(
        "images",
        [],
        visual_candidates=[
            {"label": "Images", "bbox": {"left": 100, "top": 100, "right": 180, "bottom": 140}, "confidence": 0.82},
            {"label": "Images", "bbox": {"left": 300, "top": 100, "right": 380, "bottom": 140}, "confidence": 0.78},
        ],
    )

    assert element is None
