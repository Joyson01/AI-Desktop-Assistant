import speech_recognition as sr

class SpeechService:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.calibrated = False
        self._available_override = None

    @property
    def is_available(self):
        if self._available_override is not None:
            return self._available_override
        try:
            with sr.Microphone():
                return True
        except Exception:
            return False

    @is_available.setter
    def is_available(self, value):
        self._available_override = value

    def listen(self):
        try:
            with sr.Microphone() as source:
                if not self.calibrated:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    self.calibrated = True
                try: return self.recognizer.listen(source, timeout=5, phrase_time_limit=8)
                except sr.WaitTimeoutError: return None
        except (OSError, AttributeError) as error:
            if not self._error_reported:
                print(f"[ERROR] component=stt_listen exception={type(error).__name__}: {error}")
                self._error_reported = True
            return None
    def speech_to_text(self, audio):
        if audio is None: return ""
        try: return self.recognizer.recognize_google(audio, language="en-IN").strip().lower()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as error:
            print(f"[ERROR] component=stt_transcription exception={type(error).__name__}: {error}")
            return ""
