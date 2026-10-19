from pywinauto import Desktop

command = input("Command: ").strip()

prefixes = [
    "search ",
    "search for ",
    "google search ",
]

search_text = None

lower_command = command.lower()

for prefix in prefixes:
    if lower_command.startswith(prefix):
        search_text = command[len(prefix):].strip()
        break

if search_text:
    print("Search text:", search_text)

    windows = Desktop(backend="uia").windows()

    for window in windows:
        if "Google Chrome" in window.window_text():

            edits = window.descendants(control_type="Edit")

            if edits:
                search_box = edits[0]

                print("Search box found!")

                search_box.click_input()
                search_box.type_keys(
                    search_text,
                    with_spaces=True
                )
                search_box.type_keys("{ENTER}")

                print("Search submitted!")

            else:
                print("Search box NOT found!")

            break

else:
    print("Command unclear.")