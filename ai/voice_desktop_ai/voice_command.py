import speech_recognition as sr
from pywinauto import Desktop

recognizer = sr.Recognizer()

reload_words = [
    "reload",
    "reload karo",
    "रीलोड",
    "रीलोड करो",
    "लोड करो"
]

print("Bolo...")

with sr.Microphone() as source:
    recognizer.adjust_for_ambient_noise(source, duration=1)
    audio = recognizer.listen(source)

try:
    command = recognizer.recognize_google(
        audio,
        language="hi-IN"
    )

    command = command.strip().lower()

    print("Aapne kaha:", command)

    if any(word in command for word in reload_words):

        windows = Desktop(backend="uia").windows()

        for window in windows:
            if "Google Chrome" in window.window_text():

                buttons = window.descendants(
                    control_type="Button"
                )

                for button in buttons:
                    try:
                        name = button.window_text()

                        if name.lower() == "reload":
                            print("Reload button found!")
                            button.click_input()
                            print("Reload clicked!")
                            break

                    except:
                        pass

                break

    else:
        print("Command unclear. Please say a supported command.")

except sr.UnknownValueError:
    print("Sorry, command samajh nahi aayi.")

except sr.RequestError as e:
    print("Speech service error:", e)