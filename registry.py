"""Known apps and websites + fuzzy resolution (soft-computing: fuzzy matching)."""
import re
from difflib import SequenceMatcher

APPS = {
    "chrome": {"aliases": ["chrome", "google chrome", "krom", "crome", "browser"], "win": "chrome", "linux": "google-chrome", "linux_alts": ["google-chrome-stable", "chromium-browser", "chromium"]},
    "firefox": {"aliases": ["firefox", "mozilla", "mozilla firefox"], "win": "firefox", "linux": "firefox", "linux_alts": ["firefox-esr"]},
    "edge": {"aliases": ["edge", "microsoft edge"], "win": "msedge", "linux": "microsoft-edge", "linux_alts": ["microsoft-edge-stable"]},
    "notepad": {"aliases": ["notepad", "note pad", "text editor", "gedit", "new document", "document", "editor", "gnome-text-editor"], "win": "notepad", "linux": "gnome-text-editor", "linux_alts": ["gedit", "mousepad", "xed", "kate", "code"]},
    "calculator": {"aliases": ["calculator", "calc", "calculater"], "win": "calc", "linux": "gnome-calculator", "linux_alts": ["kcalc", "galculator"]},
    "paint": {"aliases": ["paint", "ms paint"], "win": "mspaint", "linux": "pinta", "linux_alts": ["gimp", "krita"]},
    "file explorer": {"aliases": ["file explorer", "explorer", "files", "this pc", "my computer", "file manager"], "win": "explorer", "linux": "nautilus", "linux_alts": ["thunar", "nemo", "dolphin", "pcmanfm"]},
    "vs code": {"aliases": ["vs code", "vscode", "code", "visual studio code"], "win": "code", "linux": "code", "linux_alts": ["code-oss", "codium"]},
    "word": {"aliases": ["word", "ms word", "microsoft word"], "win": "winword", "linux": "libreoffice", "linux_alts": ["libreoffice --writer"]},
    "excel": {"aliases": ["excel", "ms excel"], "win": "excel", "linux": "libreoffice", "linux_alts": ["libreoffice --calc"]},
    "powerpoint": {"aliases": ["powerpoint", "ppt", "ms powerpoint"], "win": "powerpnt", "linux": "libreoffice", "linux_alts": ["libreoffice --impress"]},
    "command prompt": {"aliases": ["cmd", "command prompt", "terminal"], "win": "cmd", "linux": "x-terminal-emulator", "linux_alts": ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"]},
    "settings": {"aliases": ["settings", "setting"], "win": "ms-settings:", "linux": "gnome-control-center", "linux_alts": ["unity-control-center", "xfce4-settings-manager"]},
    "task manager": {"aliases": ["task manager"], "win": "taskmgr", "linux": "gnome-system-monitor", "linux_alts": ["ksysguard", "xfce4-taskmanager"]},
    "calendar": {"aliases": ["calendar"], "win": "outlookcal:", "linux": "gnome-calendar", "linux_alts": []},
    "clocks": {"aliases": ["clocks", "clock"], "win": "", "linux": "gnome-clocks", "linux_alts": []},
    "disks": {"aliases": ["disks", "disk manager", "disk utility"], "win": "diskmgmt.msc", "linux": "gnome-disks", "linux_alts": []},
}

SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "wikipedia": "https://www.wikipedia.org",
    "amazon": "https://www.amazon.in",
    "github": "https://github.com",
    "whatsapp": "https://web.whatsapp.com",
    "spotify": "https://open.spotify.com",
    "netflix": "https://www.netflix.com",
}

APP_ALIASES = {alias: canon for canon, d in APPS.items() for alias in d["aliases"]}
DOMAIN_RE = re.compile(r"(?:https?://)?[\w.-]+\.(?:com|in|org|net|edu|io|co|ai|gov)(?:/\S*)?", re.I)


def resolve(name: str):
    """Return (kind, target, confidence, label). kind is 'app' or 'site'."""
    key = re.sub(r"^(?:the|my|app|application)\s+", "", name.strip().lower())
    key = re.sub(r"\s+(?:app|application)$", "", key)
    if DOMAIN_RE.fullmatch(key):
        return "site", (key if key.startswith("http") else "https://" + key), 1.0, key
    if key in APP_ALIASES:
        canon = APP_ALIASES[key]
        return "app", canon, 1.0, canon
    if key in SITES:
        return "site", SITES[key], 1.0, key
    pool = [(a, "app", c) for a, c in APP_ALIASES.items()] + [(s, "site", u) for s, u in SITES.items()]
    best = max(pool, key=lambda p: SequenceMatcher(None, key, p[0]).ratio())
    score = round(SequenceMatcher(None, key, best[0]).ratio(), 2)
    label = best[2] if best[1] == "app" else best[0]
    return best[1], best[2], score, label
