import time
import os
import sys
import json
import fnmatch
import threading
import win32gui
import win32process
import win32api
import win32con
from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem as TrayMenuItem
from PIL import Image, ImageDraw
from switch_profile import switch_profile

APP_DIR = os.path.dirname(
    os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
)
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
LOG_FILE = os.path.join(APP_DIR, "auto_switch.log")
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

KNOWN_APP_ALIASES = {
    # When the user maps LoL, keep the same profile across Riot/LoL front processes.
    "league of legends.exe": {
        "league of legends.exe",
        "leagueclient.exe",
        "leagueclientux.exe",
        "leagueclientuxrender.exe",
        "leaguecrashhandler64.exe",
        "riotclientservices.exe",
        "riotclientcrashhandler.exe",
    },
}

# Global State
config = json.loads(json.dumps(DEFAULT_CONFIG))
current_profile = -1
running = True
icon = None
switch_lock = threading.Lock()
pending_switch_request = None
POLL_INTERVAL_SEC = 0.5
SWITCH_RETRY_COOLDOWN_SEC = 3.0


def log_event(message):
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def load_config():
    global config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        _normalize_config()
        print(f"Loaded config: {config}")
        log_event(f"config_loaded path={CONFIG_FILE} value={config}")
    except FileNotFoundError:
        print("Config not found, using default.")
        config = json.loads(json.dumps(DEFAULT_CONFIG))
        _normalize_config()
        save_config()  # Create default file
        log_event(f"config_created_default path={CONFIG_FILE} value={config}")
    except Exception as e:
        print(f"Error loading config: {e}")
        log_event(f"config_load_error error={e}")


def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        log_event(f"config_saved path={CONFIG_FILE}")
    except Exception as e:
        print(f"Error saving config: {e}")
        log_event(f"config_save_error error={e}")


def _normalize_config():
    global config
    if not isinstance(config, dict):
        config = {}

    try:
        config["default_profile"] = int(config.get("default_profile", 1))
    except Exception:
        config["default_profile"] = 1

    raw_mappings = config.get("mappings", {})
    mappings = {}
    if isinstance(raw_mappings, dict):
        for k, v in raw_mappings.items():
            key = str(k).strip().lower()
            if not key:
                continue
            try:
                mappings[key] = int(v)
            except Exception:
                continue
    config["mappings"] = mappings

    raw_ignore = config.get("ignore_processes", [])
    ignore = []
    if isinstance(raw_ignore, list):
        for p in raw_ignore:
            name = str(p).strip().lower()
            if name:
                ignore.append(name)
    config["ignore_processes"] = ignore


def _resolve_target_profile(active_exe):
    mappings = config.get("mappings", {})
    default_profile = config.get("default_profile", 1)

    if active_exe in mappings:
        return mappings[active_exe]

    # Optional wildcard support, e.g. "leagueclient*.exe": 2
    for pattern, profile in mappings.items():
        if ("*" in pattern or "?" in pattern or "[" in pattern) and fnmatch.fnmatch(
            active_exe, pattern
        ):
            return profile

    for canonical, aliases in KNOWN_APP_ALIASES.items():
        if canonical in mappings and active_exe in aliases:
            return mappings[canonical]

    return default_profile


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
    global current_profile, running, pending_switch_request

    last_app_logged = ""
    last_target_logged = None
    icon.visible = True

    while running:
        try:
            # Reload config dynamically? Maybe overkill, let's stick to initial load for now.
            # Or reload if file changed? For simplicity, restart app to reload.

            active_exe = get_active_process_name()

            if active_exe:
                if active_exe in config.get("ignore_processes", []):
                    time.sleep(POLL_INTERVAL_SEC)
                    continue

                if active_exe != last_app_logged:
                    # print(f"Active: {active_exe}")
                    last_app_logged = active_exe
                    log_event(f"active_exe={active_exe}")

                target_profile = _resolve_target_profile(active_exe)
                if target_profile != last_target_logged:
                    last_target_logged = target_profile
                    log_event(
                        f"target_profile={target_profile} reason_exe={active_exe} current_profile={current_profile}"
                    )

                if target_profile != current_profile:
                    with switch_lock:
                        pending_switch_request = {
                            "profile": target_profile,
                            "reason": active_exe,
                            "requested_at": time.monotonic(),
                        }

            time.sleep(POLL_INTERVAL_SEC)

        except Exception as e:
            print(f"Error in loop: {e}")
            time.sleep(POLL_INTERVAL_SEC)


def switch_worker_loop(icon):
    global current_profile, running, pending_switch_request

    last_switch_attempt_profile = None
    last_switch_attempt_at = 0.0

    while running:
        request = None
        try:
            with switch_lock:
                if pending_switch_request is not None:
                    request = pending_switch_request
                    pending_switch_request = None

            if request is None:
                time.sleep(0.05)
                continue

            target_profile = request["profile"]
            reason = request["reason"]

            if target_profile == current_profile:
                continue

            now = time.monotonic()
            if (
                target_profile == last_switch_attempt_profile
                and now - last_switch_attempt_at < SWITCH_RETRY_COOLDOWN_SEC
            ):
                with switch_lock:
                    if pending_switch_request is None:
                        pending_switch_request = request
                time.sleep(0.05)
                continue

            last_switch_attempt_profile = target_profile
            last_switch_attempt_at = now

            print(f"Switching to Profile {target_profile} (Reason: {reason})")
            log_event(f"switch_attempt profile={target_profile} reason={reason}")
            success = switch_profile(target_profile)

            if success:
                current_profile = target_profile
                icon.notify(f"Switched to Profile {target_profile}", "EG Auto-Switch")
                log_event(f"switch_success profile={target_profile}")
            else:
                log_event(f"switch_failed profile={target_profile}")
                with switch_lock:
                    if pending_switch_request is None:
                        pending_switch_request = request

        except Exception as e:
            print(f"Error in switch worker: {e}")
            log_event(f"switch_worker_error error={e}")
            time.sleep(0.2)


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
    log_event("app_start")
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

    worker = threading.Thread(target=switch_worker_loop, args=(icon,))
    worker.daemon = True
    worker.start()

    icon.run()


if __name__ == "__main__":
    main()
