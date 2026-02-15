import sys
import argparse
import time
from pywinauto.application import Application


def switch_profile(profile_number):
    try:
        # Connect to existing application
        # print(f"Connecting to EG Tool...")
        app = Application(backend="uia").connect(path="elecomui.exe")

        # Get the main window
        win = app.window(title_re=".*EG Tool.*")

        if not win.exists():
            print("Error: EG Tool window not found.")
            return False

        # Determine if we need to minimize later
        should_minimize = True
        try:
            if (
                win.check_pattern_interface("Window")
                and win.iface_window.CurrentWindowVisualState == 2
            ):  # Minimized
                should_minimize = True
        except:
            pass

        # Searching for 'ListBox'
        list_boxes = win.descendants(control_type="List")
        if not list_boxes:
            print("Error: No ListBoxes found.")
            return False

        candidates = []
        for lb in list_boxes:
            try:
                if len(lb.children(control_type="ListItem")) >= profile_number:
                    candidates.append(lb)
            except:
                pass

        if not candidates:
            print(f"Error: No list has enough items.")
            return False

        # Pick the best candidate (heuristic: last one)
        target_list_box = candidates[-1]
        items = target_list_box.children(control_type="ListItem")
        target_item = items[profile_number - 1]

        # Attempt to Invoke BUTTON inside the item ONLY.
        # DO NOT SELECT the item, as that usually focuses the UI.
        buttons = target_item.descendants(control_type="Button")
        if buttons:
            try:
                # print(f"Invoking profile button...")
                buttons[0].invoke()
            except Exception as e:
                # print(f"Invoke failed: {e}")
                # Fallback to Click Input only if Invoke fails (this moves mouse)
                # buttons[0].click_input()
                return False
        else:
            # print("No buttons found. Trying invoke on item...")
            try:
                target_item.invoke()
            except:
                return False

        # Force minimize to ensure it stays hidden/goes back
        # This handles the "pop up" issue
        try:
            win.minimize()
        except:
            pass

        return True

    except Exception as e:
        print(f"An error occurred: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Switch EG Tool Profile")
    parser.add_argument(
        "-p", "--profile", type=int, required=True, help="Profile number (1-3)"
    )
    args = parser.parse_args()
    switch_profile(args.profile)
