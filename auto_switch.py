import time
import os
import sys
import json
import threading
import win32gui
import win32process
import win32api
import win32con
from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem as TrayMenuItem
from PIL import Image, ImageDraw
from switch_profile import switch_profile

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "default_profile": 1,
    "mappings": {"league of legends.exe": 2},
    "ignore_processes": [
        "elecomui.exe",
        "python.exe",
        "powershell.exe",
        "cmd.exe",
        "conhost.exe",
    ],
}

# Global State
config = DEFAULT_CONFIG
current_profile = -1
running = True
icon = None


def load_config():
    global config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        print(f"Loaded config: {config}")
    except FileNotFoundError:
        print("Config not found, using default.")
        config = DEFAULT_CONFIG
        save_config()  # Create default file
    except Exception as e:
        print(f"Error loading config: {e}")


def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")


def create_image():
    # Generate an image for the tray icon
    width = 64
    height = 64
    image = Image.new("RGB", (width, height), (255, 255, 255))
    dc = ImageDraw.Draw(image)
    dc.rectangle((width // 2, 0, width, height // 2), fill=(0, 0, 255))
    dc.rectangle((0, height // 2, width // 2, height), fill=(255, 0, 0))
    return image


def get_active_process_name():
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None

        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        try:
            handle = win32api.OpenProcess(
                win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                False,
                pid,
            )
            if handle:
                path = win32process.GetModuleFileNameEx(handle, 0)
                win32api.CloseHandle(handle)
                return os.path.basename(path).lower()
        except:
            pass
        return None
    except:
        return None


def monitor_loop(icon):
    global current_profile, running

    last_app_logged = ""
    icon.visible = True

    while running:
        try:
            # Reload config dynamically? Maybe overkill, let's stick to initial load for now.
            # Or reload if file changed? For simplicity, restart app to reload.

            active_exe = get_active_process_name()

            if active_exe:
                if active_exe in config.get("ignore_processes", []):
                    time.sleep(1)
                    continue

                if active_exe != last_app_logged:
                    # print(f"Active: {active_exe}")
                    last_app_logged = active_exe

                target_profile = config.get("default_profile", 1)
                mappings = config.get("mappings", {})

                if active_exe in mappings:
                    target_profile = mappings[active_exe]

                if target_profile != current_profile:
                    print(
                        f"Switching to Profile {target_profile} (Reason: {active_exe})"
                    )
                    success = switch_profile(target_profile)

                    if success:
                        current_profile = target_profile
                        icon.notify(
                            f"Switched to Profile {target_profile}", "EG Auto-Switch"
                        )
                    else:
                        pass

            time.sleep(1)

        except Exception as e:
            print(f"Error in loop: {e}")
            time.sleep(1)


def on_exit(icon, item):
    global running
    running = False
    icon.stop()


def open_config(icon, item):
    # Open config.json in default editor
    try:
        os.startfile(CONFIG_FILE)
    except Exception as e:
        print(f"Error opening config: {e}")


def reload_config(icon, item):
    load_config()
    icon.notify("Configuration reloaded.", "EG Auto-Switch")


def main():
    load_config()

    image = create_image()
    menu = TrayMenu(
        TrayMenuItem("Open Config", open_config),
        TrayMenuItem("Reload Config", reload_config),
        TrayMenuItem("Exit", on_exit),
    )

    global icon
    icon = TrayIcon("EG Auto-Switch", image, "EG Auto-Switch", menu)

    # Run loop in background thread
    t = threading.Thread(target=monitor_loop, args=(icon,))
    t.daemon = True
    t.start()

    icon.run()


if __name__ == "__main__":
    main()
