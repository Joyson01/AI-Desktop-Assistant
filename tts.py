"""Text-to-speech. Linux: spd-say / espeak-ng (reliable). Windows: pyttsx3 (SAPI)."""
import logging
import shutil
import subprocess

log = logging.getLogger("maruti.tts")


class Speaker:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def say(self, text: str):
        print(f"Maruti: {text}")
        if not self.enabled:
            return
        try:
            for cmd in (["spd-say", "-w"], ["espeak-ng"], ["espeak"]):
                if shutil.which(cmd[0]):
                    subprocess.run(cmd + [text], stderr=subprocess.DEVNULL, check=False)
                    return
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            log.warning("TTS failed: %s", exc)
