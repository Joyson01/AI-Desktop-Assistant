import speech_recognition as sr
import webbrowser

recognizer = sr.Recognizer()

print("Bolo...")

with sr.Microphone() as source:
    recognizer.adjust_for_ambient_noise(source, duration=1)
    audio = recognizer.listen(source)

try:
    command = recognizer.recognize_google(
        audio,
        language="hi-IN"
    )

    command = command.strip()

    print("Aapne kaha:", command)

    open_text = None

    if "ओपन करो" in command:

        open_text = command.split("ओपन करो")[0]

        if "गूगल पर" in open_text:
            open_text = open_text.replace(
                "गूगल पर",
                ""
            )

        # Extra spaces remove
        open_text = open_text.strip()

        print("Open text:", open_text)

    if open_text:

        websites = {
            "इंस्टाग्राम": "https://www.instagram.com",
            "यूट्यूब": "https://www.youtube.com",
            "युटुब": "https://www.youtube.com",
            "यूटुब": "https://www.youtube.com",
            "गूगल": "https://www.google.com"
        }

        url = websites.get(open_text)

        if url:
            print("Opening:", open_text)
            webbrowser.open(url)
            print("Website opened!")
        else:
            print("Website not supported yet.")

    else:
        print("Open command unclear.")

except sr.UnknownValueError:
    print("Sorry, command samajh nahi aayi.")

except sr.RequestError as e:
    print("Speech service error:", e)