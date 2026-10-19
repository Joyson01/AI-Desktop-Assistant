import pyautogui
import pytesseract
import time

from PIL import ImageGrab
from pytesseract import Output


TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def find_text(target):

    print("Looking for:", target)

    screenshot = ImageGrab.grab()

    data = pytesseract.image_to_data(
        screenshot,
        lang="hin+eng",
        output_type=Output.DICT
    )

    target = target.lower().strip()

    for i in range(len(data["text"])):

        text = data["text"][i].strip()

        if not text:
            continue

        if target in text.lower():

            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]

            center_x = x + w // 2
            center_y = y + h // 2

            print("Found:", text)
            print("Position:", center_x, center_y)

            return center_x, center_y

    return None


print("OCR Click Test")
print("Chrome/VS Code screen par koi visible text rakho.")

target = input("Kis text par click karna hai: ")

position = find_text(target)

if position:

    x, y = position

    print("Clicking:", x, y)

    time.sleep(1)

    pyautogui.click(x, y)

    print("Clicked!")

else:

    print("Text nahi mila.")
    click_on_text("file")