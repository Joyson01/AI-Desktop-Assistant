import os
import shutil
import subprocess
import time


APP_REGISTRY = {
    "explorer": {
        "name": "File Explorer",
        "aliases": ["explorer", "file explorer", "windows explorer", "files", "file manager", "फाइल एक्सप्लोरर", "file explorer kholo"],
        "executable_names": ["explorer.exe", "nautilus", "dolphin", "thunar", "pcmanfm"],
        "known_paths": [r"C:\\Windows\\explorer.exe"],
    },
    "notepad": {
        "name": "Notepad",
        "aliases": ["notepad", "note pad", "notes", "नोटपैड", "नोट पैड", "notepad kholo", "notes kholo"],
        "executable_names": ["notepad.exe", "gedit", "gnome-text-editor", "kate", "mousepad"],
        "known_paths": [r"C:\\Windows\\System32\\notepad.exe"],
    },
    "chrome": {
        "name": "Google Chrome",
        "aliases": ["chrome", "google chrome", "google browser", "क्रोम", "गूगल क्रोम", "chrome kholo"],
        "executable_names": ["chrome.exe", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
        "known_paths": [
            r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            r"%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe",
        ],
    },
    "edge": {
        "name": "Microsoft Edge",
        "aliases": ["edge", "microsoft edge", "ms edge", "एज", "माइक्रोसॉफ्ट एज", "edge kholo"],
        "executable_names": ["msedge.exe", "microsoft-edge", "microsoft-edge-stable"],
        "known_paths": [
            r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
            r"C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
        ],
    },
    "vscode": {
        "name": "Visual Studio Code",
        "aliases": ["vs code", "visual studio code", "vscode", "code", "वीएस कोड", "कोड", "vs code kholo", "vscode kholo"],
        "executable_names": ["code.exe", "Code.exe", "code"],
        "known_paths": [
            r"C:\\Program Files\\Microsoft VS Code\\Code.exe",
            r"C:\\Program Files (x86)\\Microsoft VS Code\\Code.exe",
        ],
    },
    "word": {
        "name": "Microsoft Word",
        "aliases": ["word", "microsoft word", "ms word", "वर्ड", "माइक्रोसॉफ्ट वर्ड", "word kholo"],
        "executable_names": ["winword.exe"],
        "known_paths": [
            r"C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE",
            r"C:\\Program Files (x86)\\Microsoft Office\\root\\Office16\\WINWORD.EXE",
        ],
    },
    "calculator": {
        "name": "Calculator",
        "aliases": ["calculator", "calc", "कैलकुलेटर"],
        "executable_names": ["calc.exe", "gnome-calculator", "kcalc"],
        "known_paths": [r"C:\\Windows\\System32\\calc.exe"],
    },
    "paint": {
        "name": "Paint",
        "aliases": ["paint", "mspaint"],
        "executable_names": ["mspaint.exe", "drawing", "kolourpaint"],
        "known_paths": [r"C:\\Windows\\System32\\mspaint.exe"],
    },
    "settings": {
        "name": "Settings",
        "aliases": ["settings", "system settings", "setting"],
        "executable_names": ["SystemSettings.exe", "gnome-control-center"],
        "known_paths": [r"C:\\Windows\\ImmersiveControlPanel\\SystemSettings.exe"],
    },
    "taskmgr": {
        "name": "Task Manager",
        "aliases": ["task manager", "taskmgr"],
        "executable_names": ["taskmgr.exe", "gnome-system-monitor"],
        "known_paths": [r"C:\\Windows\\System32\\Taskmgr.exe"],
    },
    "cmd": {
        "name": "Command Prompt",
        "aliases": ["command prompt", "cmd", "terminal command", "command"],
        "executable_names": ["cmd.exe", "gnome-terminal", "konsole", "xterm"],
        "known_paths": [r"C:\\Windows\\System32\\cmd.exe"],
    },
    "powershell": {
        "name": "PowerShell",
        "aliases": ["powershell", "power shell"],
        "executable_names": ["powershell.exe", "pwsh"],
        "known_paths": [r"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"],
    },
}


AMBIGUOUS_NAMES = {
    "file": "Do you mean File Explorer?",
    "code": "Do you mean Visual Studio Code?",
    "browser": "Do you mean Chrome or Edge?",
    "notes": "Do you mean Notepad?",
}


def _normalize_alias(value):
    text = str(value or "").strip().lower()
    text = text.replace("_", " ")
    text = text.replace("-", " ")
    text = " ".join(text.split())
    return text


def _expand_environment(path):
    if not path:
        return path
    return os.path.expandvars(path)


def _search_path_and_known_locations(executable_names, known_paths):
    for executable_name in executable_names:
        found = shutil.which(executable_name)
        if found:
            return {"target": found, "launch_method": "path"}
    for candidate in known_paths:
        expanded = _expand_environment(candidate)
        if expanded and os.path.exists(expanded):
            return {"target": expanded, "launch_method": "known_path"}
    return {"target": None, "launch_method": None}


def _find_start_menu_shortcut(app_key):
    start_dirs = [
        os.path.join(os.environ.get("PROGRAMDATA", r"C:\\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("APPDATA", r"C:\\Users\\Default\\AppData\\Roaming"), "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    app_record = APP_REGISTRY.get(app_key, {})
    names = {name.lower() for name in app_record.get("aliases", [])} | {app_record.get("name", "").lower()}
    for directory in start_dirs:
        if not os.path.isdir(directory):
            continue
        for root, _, files in os.walk(directory):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                lowered = os.path.splitext(file_name)[0].lower()
                if any(alias in lowered for alias in ["chrome", "edge", "code", "word", "notepad", "explorer"] if alias in names):
                    return {"target": full_path, "launch_method": "start_menu"}
    return {"target": None, "launch_method": None}


def _build_ambiguous_response(name):
    return {
        "found": False,
        "name": None,
        "canonical": None,
        "launch_method": None,
        "target": None,
        "confidence": 0.0,
        "reason": AMBIGUOUS_NAMES.get(name, "Application not found"),
    }


def resolve_application(app_name):
    query = _normalize_alias(app_name)
    if not query:
        return {"found": False, "name": None, "canonical": None, "launch_method": None, "target": None, "confidence": 0.0, "reason": "Application not specified"}

    if query in AMBIGUOUS_NAMES:
        return _build_ambiguous_response(query)

    for canonical, details in APP_REGISTRY.items():
        alias_set = {alias.lower() for alias in details.get("aliases", [])}
        if query == canonical or query in alias_set:
            direct = _search_path_and_known_locations(details.get("executable_names", []), details.get("known_paths", []))
            start_menu = _find_start_menu_shortcut(canonical)
            target = direct["target"] or start_menu["target"]
            method = direct["launch_method"] or start_menu["launch_method"] or "shell"
            return {
                "found": bool(target),
                "name": details.get("name"),
                "canonical": canonical,
                "launch_method": method,
                "target": target,
                "confidence": 0.98 if target else 0.0,
                "reason": None if target else "Application not found",
            }

    for canonical, details in APP_REGISTRY.items():
        alias_set = {alias.lower() for alias in details.get("aliases", [])}
        if any(word in query for word in ["file", "code", "browser", "note"]) and any(alias in query for alias in alias_set):
            continue
        if any(alias in query for alias in alias_set):
            direct = _search_path_and_known_locations(details.get("executable_names", []), details.get("known_paths", []))
            start_menu = _find_start_menu_shortcut(canonical)
            target = direct["target"] or start_menu["target"]
            method = direct["launch_method"] or start_menu["launch_method"] or "shell"
            return {
                "found": bool(target),
                "name": details.get("name"),
                "canonical": canonical,
                "launch_method": method,
                "target": target,
                "confidence": 0.9 if target else 0.0,
                "reason": None if target else "Application not found",
            }

    if query in {"file", "files"}:
        return _build_ambiguous_response("file")
    if query in {"code", "vscode", "visual studio code"}:
        return _build_ambiguous_response("code")
    if query in {"browser", "google browser"}:
        return _build_ambiguous_response("browser")

    return {
        "found": False,
        "name": None,
        "canonical": None,
        "launch_method": None,
        "target": None,
        "confidence": 0.0,
        "reason": "Application not found",
    }


def launch_application(app_name):
    discovery = resolve_application(app_name)
    if not discovery.get("found"):
        return {"success": False, "application": None, "message": discovery.get("reason") or "Application not found"}

    target = discovery.get("target")
    if target and os.path.exists(target):
        try:
            subprocess.Popen([target], shell=False)
            return {"success": True, "application": discovery.get("canonical"), "message": f"{discovery.get('name')} is open."}
        except Exception as exc:
            return {"success": False, "application": discovery.get("canonical"), "message": f"I couldn't open {discovery.get('name')}: {exc}"}

    if discovery.get("canonical") == "explorer":
        try:
            subprocess.Popen(["explorer.exe"], shell=False)
            return {"success": True, "application": "explorer", "message": "File Explorer is open."}
        except Exception as exc:
            return {"success": False, "application": "explorer", "message": f"I couldn't open File Explorer: {exc}"}

    if discovery.get("canonical") == "notepad":
        try:
            subprocess.Popen(["notepad.exe"], shell=False)
            return {"success": True, "application": "notepad", "message": "Notepad is open."}
        except Exception as exc:
            return {"success": False, "application": "notepad", "message": f"I couldn't open Notepad: {exc}"}

    return {"success": False, "application": discovery.get("canonical"), "message": f"I couldn't verify that {discovery.get('name')} opened."}


def verify_application_launch(app_name):
    discovery = resolve_application(app_name)
    if not discovery.get("found"):
        return False
    time.sleep(0.5)
    return bool(discovery.get("target"))
