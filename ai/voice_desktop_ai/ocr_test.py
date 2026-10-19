import pyautogui
import pytesseract
from PIL import ImageGrab
from pytesseract import Output


pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


print("Taking screenshot...")

screenshot = ImageGrab.grab()

data = pytesseract.image_to_data(
    screenshot,
    lang="hin+eng",
    output_type=Output.DICT
)

print("\n========== SCREEN WORDS ==========\n")

for i in range(len(data["text"])):

    text = data["text"][i].strip()

    if not text:
        continue

    confidence = data["conf"][i]

    try:
        confidence = float(confidence)
    except:
        confidence = 0

    if confidence < 30:
        continue

    x = data["left"][i]
    y = data["top"][i]
    w = data["width"][i]
    h = data["height"][i]

    center_x = x + (w // 2)
    center_y = y + (h // 2)

    print(
        f"Text: {text} | "
        f"Position: ({center_x}, {center_y}) | "
        f"Confidence: {confidence:.0f}"
    )

print("\n==================================")
