import shutil
import subprocess

_listeners = []


def add_speech_listener(callback):
    """Register a listener callback to receive spoken messages."""
    if callback not in _listeners:
        _listeners.append(callback)


def remove_speech_listener(callback):
    """Unregister a speech listener callback."""
    if callback in _listeners:
        _listeners.remove(callback)


def speak(message):
    print(f"Assistant: {message}")
    for listener in list(_listeners):
        try:
            listener(str(message))
        except Exception:
            pass
    escaped = str(message).replace("'", "''")
    try:
        if shutil.which("powershell"):
            subprocess.Popen(["powershell", "-NoProfile", "-Command", "Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Rate=-1; $s.Speak('" + escaped + "')"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        elif shutil.which("spd-say"):
            subprocess.Popen(["spd-say", "-r", "-10", str(message)])
    except OSError:
        pass
