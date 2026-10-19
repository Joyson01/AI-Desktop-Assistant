import re


VARIANTS = {
    "फाइल": "file", "फाईल": "file", "फाइल्स": "files",
    "सेलेक्ट": "select", "सिलेक्ट": "select", "सिलेक्‍ट": "select",
    "कॉपी": "copy", "कोपी": "copy", "पेस्ट": "paste",
    "क्लिक": "click", "एंटर": "enter", "इंटर": "enter",
    "स्क्रॉल": "scroll", "स्क्रोल": "scroll", "क्रोम": "chrome",
    "यूट्यूब": "youtube", "युटुब": "youtube", "इंस्टाग्राम": "instagram",
    "ब्लूटूथ": "bluetooth", "ब्लू टूथ": "bluetooth", "bluetooh": "bluetooth",
    "वाईफाई": "wifi", "वाई फाई": "wifi", "wi fi": "wifi", "you tube": "youtube",
    "d chrome": "chrome", "de chrome": "chrome",
    "चालू": "on", "बंद": "off", "band": "off", "chalu": "on",
}


def normalize_command(transcript):
    """Normalize command words while preserving text after a type command."""
    raw = str(transcript or "").strip()
    if not raw:
        return ""
    if re.match(r"^\s*(type|टाइप)\b", raw, re.IGNORECASE):
        return raw
    normalized = raw.lower()
    for source, replacement in VARIANTS.items():
        normalized = normalized.replace(source, replacement)
    normalized = re.sub(r"(खोलना है|खोलो|कर दो|करो|चाहिए|kholo|karo|kar do|please)", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized.startswith("turn "):
        normalized = normalized.replace("turn ", "", 1)
    return " ".join(normalized.split())
