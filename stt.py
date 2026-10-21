"""Speech-to-text using SpeechRecognition + Google Web Speech (en-IN first, then hi-IN)."""
import speech_recognition as sr


def list_mics():
    for i, name in enumerate(sr.Microphone.list_microphone_names()):
        print(f"{i}: {name}")


class Listener:
    def __init__(self, device_index=None):
        self.rec = sr.Recognizer()
        self.rec.dynamic_energy_threshold = True
        self.mic = sr.Microphone(device_index=device_index)
        with self.mic as src:
            self.rec.adjust_for_ambient_noise(src, duration=1)
        print(f"[mic] ready, energy threshold = {self.rec.energy_threshold:.0f}")

    def listen(self, timeout=6, phrase_limit=8):
        print("[listening...]", flush=True)
        with self.mic as src:
            try:
                audio = self.rec.listen(src, timeout=timeout, phrase_time_limit=phrase_limit)
            except sr.WaitTimeoutError:
                print("[no speech heard - check the mic device / volume]")
                return None
        print("[recognizing...]", flush=True)
        for lang in ("en-IN", "hi-IN"):
            try:
                return self.rec.recognize_google(audio, language=lang)
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                print(f"[speech service error - internet?] {exc}")
                return None
        print("[heard something but could not understand it]")
        return None
