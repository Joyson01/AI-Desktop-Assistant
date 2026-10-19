from brain.phonetic_matcher import choose_confident_candidate, phonetic_similarity, score_candidate
from uia_engine import UIElement, find_element


def test_requested_multilingual_pronunciations_match_visible_text(monkeypatch):
    monkeypatch.setattr("uia_engine._ocr_find_target", lambda target: None)
    for spoken, visible in (
        ("Chat G P T", "ChatGPT"),
        ("You Tube", "YouTube"),
        ("गूगल", "Google"),
        ("क्रोम", "Chrome"),
        ("यूट्यूब", "YouTube"),
    ):
        assert phonetic_similarity(spoken, visible) >= 0.80
        result = find_element(spoken, [UIElement(visible, "Button", "", (0, 0, 10, 10), True, True)])
        assert result is not None


def test_homophones_are_ambiguous_even_when_one_is_exact():
    elements = [
        UIElement("Mail", "Button", "", (0, 0, 10, 10), True, True),
        UIElement("Male", "Button", "", (20, 0, 30, 10), True, True),
    ]
    assert find_element("mail", elements) is None


def test_exact_text_beats_a_non_homophonic_phonetic_candidate():
    elements = [
        UIElement("ChargeGPT", "Button", "", (0, 0, 10, 10), True, True),
        UIElement("ChatGPT", "Button", "", (20, 0, 30, 10), True, True),
    ]
    assert find_element("chatgpt", elements).name == "ChatGPT"


def test_unrelated_candidates_do_not_pass_confidence_gate():
    scored = [score_candidate("corrupted speech", "Settings")]
    assert choose_confident_candidate(scored) is None