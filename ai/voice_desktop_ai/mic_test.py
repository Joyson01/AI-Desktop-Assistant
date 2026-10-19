import speech_recognition as sr

MIC_INDEX = 1

recognizer = sr.Recognizer()

recognizer.energy_threshold = 300
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.8
recognizer.phrase_threshold = 0.3
recognizer.non_speaking_duration = 0.5

print("======================================")
print("        MICROPHONE TEST")
print("======================================")

microphones = sr.Microphone.list_microphone_names()

for i, name in enumerate(microphones):
    print(f"{i}: {name}")

print()
print("Selected microphone:")
print(MIC_INDEX, microphones[MIC_INDEX])

print()
print("Calibrating microphone...")
print("Please stay quiet for 2 seconds.")

try:
    with sr.Microphone(device_index=MIC_INDEX) as source:

        recognizer.adjust_for_ambient_noise(
            source,
            duration=2
        )

        print()
        print("======================================")
        print("MIC ON - BOLO: hello assistant")
        print("======================================")

        audio = recognizer.listen(
            source,
            timeout=8,
            phrase_time_limit=6
        )

    print()
    print("Audio received!")
    print("Recognizing...")

    text = recognizer.recognize_google(
        audio,
        language="en-IN"
    )

    print()
    print("You said:", text)

except sr.WaitTimeoutError:
    print()
    print("ERROR: Microphone ON hua, lekin awaaz nahi mili.")

except sr.UnknownValueError:
    print()
    print("Microphone ne audio receive kiya,")
    print("lekin speech samajh nahi aayi.")

except sr.RequestError as e:
    print()
    print("Google Speech service error:")
    print(e)

except Exception as e:
    print()
    print("Microphone error:")
    print(type(e).__name__)
    print(e)