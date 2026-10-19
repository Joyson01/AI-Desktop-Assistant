"""Small, local pronunciation-aware matching primitives for visible targets."""

from dataclasses import dataclass
import re
import unicodedata
from difflib import SequenceMatcher


_DEVANAGARI = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऋ": "ri",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
    "ष": "sh", "स": "s", "ह": "h", "क्ष": "ksh", "त्र": "tr",
    "ज्ञ": "gy", "ड़": "d", "ढ़": "dh", "क़": "k", "ख़": "kh",
    "ग़": "g", "ज़": "z", "फ़": "f", "ड़": "d", "ढ़": "dh",
}
_VOWEL_SIGNS = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ृ": "ri"}
_INDEPENDENT_VOWELS = set("अआइईउऊएऐओऔऋ")
_VIRAMA = "्"


def transliterate(text):
    """Transliterate Devanagari without translating its meaning."""
    output = []
    chars = list(unicodedata.normalize("NFC", str(text or "")))
    index = 0
    while index < len(chars):
        char = chars[index]
        if char not in _DEVANAGARI:
            output.append(char)
            index += 1
            continue
        value = _DEVANAGARI[char]
        if char not in _INDEPENDENT_VOWELS:
            if index + 1 < len(chars) and chars[index + 1] in _VOWEL_SIGNS:
                value += _VOWEL_SIGNS[chars[index + 1]]
                index += 1
            elif index + 1 >= len(chars) or chars[index + 1] != _VIRAMA:
                value += "a"
        output.append(value)
        index += 1
    return "".join(output)


def normalize_text(text):
    value = transliterate(text).casefold()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def _roman_phonetic(value):
    value = value.replace("q", "k").replace("c", "k").replace("x", "ks")
    value = value.replace("ph", "f").replace("th", "t").replace("dh", "d")
    value = value.replace("sh", "s").replace("ch", "c")
    value = re.sub(r"([aeiou])\1+", r"\1", value)
    return value


def phonetic_normalize(text):
    normalized = normalize_text(text).replace(" ", "")
    return _roman_phonetic(normalized)


def _consonant_skeleton(text):
    return re.sub(r"[aeiou]", "", phonetic_normalize(text))


def text_similarity(left, right):
    left, right = normalize_text(left), normalize_text(right)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def token_similarity(left, right):
    left_tokens = normalize_text(left).split()
    right_tokens = normalize_text(right).split()
    if not left_tokens or not right_tokens:
        return 0.0
    return sum(max(SequenceMatcher(None, token, option).ratio() for option in right_tokens) for token in left_tokens) / len(left_tokens)


def phonetic_similarity(left, right):
    left, right = phonetic_normalize(left), phonetic_normalize(right)
    if not left or not right:
        return 0.0
    encoded_score = SequenceMatcher(None, left, right).ratio()
    left_skeleton, right_skeleton = _consonant_skeleton(left), _consonant_skeleton(right)
    skeleton_score = SequenceMatcher(None, left_skeleton, right_skeleton).ratio() if left_skeleton and right_skeleton else 0.0
    return max(encoded_score, skeleton_score)


@dataclass(frozen=True)
class TargetScore:
    raw_target: str
    normalized_target: str
    phonetic_target: str
    candidate: str
    normalized_candidate: str
    phonetic_candidate: str
    text_score: float
    phonetic_score: float
    token_score: float
    context_score: float = 0.0
    uia_score: float = 0.0
    visual_score: float = 0.0

    @property
    def final_score(self):
        return (
            0.30 * self.text_score
            + 0.40 * self.phonetic_score
            + 0.10 * self.token_score
            + 0.10 * self.context_score
            + 0.10 * self.uia_score
        )


def score_candidate(spoken_target, candidate, context=None, uia=False, visual_score=0.0):
    context = context or {}
    normalized_target = normalize_text(spoken_target)
    normalized_candidate = normalize_text(candidate)
    return TargetScore(
        raw_target=str(spoken_target or ""),
        normalized_target=normalized_target,
        phonetic_target=phonetic_normalize(spoken_target),
        candidate=str(candidate or ""),
        normalized_candidate=normalized_candidate,
        phonetic_candidate=phonetic_normalize(candidate),
        text_score=text_similarity(spoken_target, candidate),
        phonetic_score=phonetic_similarity(spoken_target, candidate),
        token_score=token_similarity(spoken_target, candidate),
        context_score=float(context.get("context_score", 0.0) or 0.0),
        uia_score=1.0 if uia else 0.0,
        visual_score=visual_score,
    )


def choose_confident_candidate(scored, minimum_confidence=0.78, minimum_margin=0.08):
    ordered = sorted(scored, key=lambda item: item.final_score, reverse=True)
    if not ordered or ordered[0].final_score < minimum_confidence:
        return None
    margin = ordered[0].final_score - (ordered[1].final_score if len(ordered) > 1 else 0.0)
    if len(ordered) > 1 and margin < minimum_margin:
        return None
    return ordered[0]