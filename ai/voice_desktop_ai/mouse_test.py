import pyautogui
import time

print("Mouse test starting...")
time.sleep(3)

x, y = pyautogui.position()
print(f"Current mouse position: {x}, {y}")