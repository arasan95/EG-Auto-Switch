import argparse
import json
import os
import struct
import subprocess
import time
from pathlib import Path

import win32file


# Packet format observed from ELECOM daemon client implementation.
_PIPE_NAME = r"\\.\pipe\85bfc8dc07b30409b80ead98fc590be5"
_PACKET_MAGIC = 67572001
_PACKET_VERSION = 1
_READ_BUFFER_SIZE = 65536

_SERVICE_START_TIMEOUT_SEC = 2.5
_LITEDB_DLL = Path(r"C:\Program Files (x86)\ELECOM\EG Tool\LiteDB.dll")
_INPUT_ROOT = Path(r"C:\ProgramData\ELECOM\ELECOM\Input")
_WRITE_DATA_EDIT_INDEX = 1

_db_packet_cache = {}
_profile_signature_cache = {}


def _eg_tool_dir():
    return Path(r"C:\Program Files (x86)\ELECOM\EG Tool")


def _hidden_subprocess_kwargs():
    if os.name != "nt":
        return {}

    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def _pipe_exists():
    try:
        return Path(_PIPE_NAME).exists()
    except Exception:
        return False


def _ensure_service_running():
    if _pipe_exists():
        return True

    tool_dir = _eg_tool_dir()
    service_exe = tool_dir / "elecom.exe"
    if not service_exe.exists():
        return False

    try:
        subprocess.Popen(
            [str(service_exe), "--service"],
            cwd=str(tool_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_hidden_subprocess_kwargs(),
        )
    except Exception:
        return False

    deadline = time.time() + _SERVICE_START_TIMEOUT_SEC
    while time.time() < deadline:
        if _pipe_exists():
            return True
        time.sleep(0.05)
    return False


def _send_message(message):
    payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    packet = struct.pack(
        "<Ihh",
        _PACKET_MAGIC,
        _PACKET_VERSION,
        len(payload),
    ) + payload

    handle = win32file.CreateFile(
        _PIPE_NAME,
        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
        0,
        None,
        win32file.OPEN_EXISTING,
        0,
        None,
    )

    try:
        win32file.WriteFile(handle, packet)
        _, raw = win32file.ReadFile(handle, _READ_BUFFER_SIZE)
    finally:
        win32file.CloseHandle(handle)

    if len(raw) < 8:
        raise RuntimeError("Daemon response is too short.")

    magic, version, payload_len = struct.unpack("<Ihh", raw[:8])
    if magic != _PACKET_MAGIC or version != _PACKET_VERSION:
        raise RuntimeError("Daemon response header is invalid.")

    data = raw[8 : 8 + payload_len]
    return json.loads(data.decode("utf-8", errors="replace"))


def _list_devices():
    response = _send_message({"schema": "pipe-1.0", "path": "/devices"})
    if response.get("status") != 200:
        raise RuntimeError(f"/devices failed: {response}")
    return response.get("content") or []


def _get_profiles(model, session):
    response = _send_message(
        {
            "schema": "pipe-1.0",
            "path": f"/{model}/profile",
            "method": 1,
            "session": session,
            "content": {},
        }
    )
    if response.get("status") != 200:
        raise RuntimeError(f"/{model}/profile failed: {response}")

    content = response.get("content")
    if not isinstance(content, list):
        raise RuntimeError(f"/{model}/profile returned invalid content: {response}")
    return content


def _get_sync_profiles(model, session):
    response = _send_message(
        {
            "schema": "pipe-1.0",
            "path": f"/{model}/sync",
            "method": 1,
            "session": session,
            "content": {},
        }
    )
    if response.get("status") != 200:
        raise RuntimeError(f"/{model}/sync failed: {response}")

    content = response.get("content")
    if not isinstance(content, dict):
        return []

    profiles = content.get("profiles")
    if not isinstance(profiles, list):
        return []
    return profiles


def _select_profile_packet(sync_profiles, profiles, profile_number):
    # Prefer /sync order (UI profile 1 => index 0).
    idx = profile_number - 1
    if 0 <= idx < len(sync_profiles):
        packet = sync_profiles[idx].get("profile")
        if packet:
            return packet

    # Some devices use 0-based onboardId while UI profile numbers are 1-based.
    fallback_id = profile_number - 1
    for p in profiles:
        if p.get("onboardId") == fallback_id and p.get("profilePacket"):
            return p.get("profilePacket")

    # Alternate fallback: exact onboardId match.
    for p in profiles:
        if p.get("onboardId") == profile_number and p.get("profilePacket"):
            return p.get("profilePacket")

    # Final fallback: pick by index from sorted onboard IDs.
    keyed = []
    for p in profiles:
        try:
            keyed.append((int(p.get("onboardId")), p.get("profilePacket")))
        except Exception:
            continue
    keyed.sort(key=lambda x: x[0])
    if keyed:
        idx = max(0, min(profile_number - 1, len(keyed) - 1))
        return keyed[idx][1]
    return None


def _pick_sync_selected_packet(sync_profiles, profile_number):
    # Observed behavior on KG839US: sync content has 2 profiles, and index 1
    # reflects the profile selected by set_current_profile_index(n).
    if len(sync_profiles) > 1:
        pkt = sync_profiles[1].get("profile")
        if pkt:
            return pkt

    # Fallback for other shapes.
    idx = max(0, profile_number - 1)
    if idx < len(sync_profiles):
        pkt = sync_profiles[idx].get("profile")
        if pkt:
            return pkt
    if sync_profiles:
        return sync_profiles[0].get("profile")
    return None


def _preferred_model_tokens():
    input_root = Path(r"C:\ProgramData\ELECOM\ELECOM\Input")
    if not input_root.exists():
        return []

    tokens = []
    for db in input_root.rglob("elecom_user_*.db"):
        name = db.stem.lower()
        # Example: elecom_user_kg839us_0 -> kg839us
        if not name.startswith("elecom_user_"):
            continue
        suffix = name[len("elecom_user_") :]
        parts = suffix.split("_")
        if not parts:
            continue
        model = parts[0]
        if model and model not in tokens:
            tokens.append(model)
    return tokens


def _choose_device(devices):
    if not devices:
        return None

    preferred = _preferred_model_tokens()
    if preferred:
        preferred_set = set(preferred)
        for device in devices:
            model = str(device.get("modelName", "")).lower()
            if model in preferred_set:
                return device

    # Fallback: first connected device.
    return devices[0]


def _find_profile_db(model):
    model_token = (model or "").strip().lower()
    if not model_token or not _INPUT_ROOT.exists():
        return None

    prefix = f"elecom_user_{model_token}_"
    candidates = []
    for db in _INPUT_ROOT.rglob("elecom_user_*.db"):
        stem = db.stem.lower()
        if stem.startswith(prefix):
            candidates.append(db)

    if not candidates:
        return None

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _load_db_profile_packets(model):
    db_path = _find_profile_db(model)
    if not db_path or not _LITEDB_DLL.exists():
        return {}

    cache_key = model.lower()
    try:
        mtime = db_path.stat().st_mtime
    except Exception:
        mtime = None

    cached = _db_packet_cache.get(cache_key)
    if (
        cached
        and cached.get("db_path") == str(db_path)
        and cached.get("mtime") == mtime
        and isinstance(cached.get("packets"), dict)
    ):
        return cached["packets"]

    db_path_ps = str(db_path).replace("'", "''")
    litedb_ps = str(_LITEDB_DLL).replace("'", "''")

    ps_script = (
        f"$DbPath = '{db_path_ps}'\n"
        f"$LiteDbPath = '{litedb_ps}'\n"
        "$ErrorActionPreference = 'Stop'\n"
        "Add-Type -Path $LiteDbPath\n"
        "$db = [LiteDB.LiteDatabase]::new($DbPath)\n"
        "try {\n"
        "    $col = $db.GetCollection('ProfileRaw')\n"
        "    foreach ($d in $col.FindAll()) {\n"
        "        $ptype = $null\n"
        "        if ($d.ContainsKey('ProfileType')) {\n"
        "            $ptype = $d['ProfileType'].AsInt32\n"
        "        }\n"
        "        if ($ptype -eq $null) { continue }\n"
        "\n"
        "        $raw = $d['ProfileRawPacket'].AsBinary\n"
        "        $packet = [Convert]::ToBase64String($raw)\n"
        "        [ordered]@{\n"
        "            type = $ptype\n"
        "            packet = $packet\n"
        "        } | ConvertTo-Json -Compress\n"
        "    }\n"
        "}\n"
        "finally {\n"
        "    $db.Dispose()\n"
        "}\n"
    )

    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                ps_script,
            ],
            capture_output=True,
            text=True,
            check=False,
            **_hidden_subprocess_kwargs(),
        )
    except Exception:
        return {}

    if proc.returncode != 0:
        return {}

    packets = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            ptype = int(item.get("type"))
            packet = item.get("packet")
            if isinstance(packet, str) and packet:
                packets[ptype] = packet
        except Exception:
            continue

    _db_packet_cache[cache_key] = {
        "db_path": str(db_path),
        "mtime": mtime,
        "packets": packets,
    }
    return packets


def _set_current_profile_index(model, session, index):
    response = _send_message(
        {
            "schema": "pipe-1.0",
            "path": f"/{model}/set_current_profile_index",
            "method": 1,
            "session": session,
            "content": {"current_profile_index": int(index)},
        }
    )
    return response.get("status") == 200


def _get_selected_sync_hash(model, session):
    profiles = _get_sync_profiles(model, session)
    if not profiles:
        return None

    pkt = None
    if len(profiles) > 1:
        pkt = profiles[1].get("profile")
    if not pkt:
        pkt = profiles[0].get("profile")
    if not pkt:
        return None

    try:
        # Keep a short stable fingerprint of the active daemon profile state.
        import hashlib

        return hashlib.sha256(pkt.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return None


def _switch_profile_via_write_data(model, session, profile_number):
    packets = _load_db_profile_packets(model)
    profile_packet = packets.get(int(profile_number))
    if not profile_packet:
        return False

    key = (model.lower(), int(profile_number))
    for _ in range(3):
        try:
            before_hash = _get_selected_sync_hash(model, session)
            if not _set_current_profile_index(model, session, _WRITE_DATA_EDIT_INDEX):
                time.sleep(0.05)
                continue

            response = _send_message(
                {
                    "schema": "pipe-1.0",
                    "path": f"/{model}/write_data",
                    "method": 1,
                    "session": session,
                    "content": {"data": profile_packet},
                }
            )
            if response.get("status") != 200:
                time.sleep(0.05)
                continue

            time.sleep(0.05)
            after_hash = _get_selected_sync_hash(model, session)
            known_hash = _profile_signature_cache.get(key)

            if after_hash:
                if known_hash and after_hash == known_hash:
                    return True
                if before_hash != after_hash:
                    _profile_signature_cache[key] = after_hash
                    return True

                # If this profile was already active, hash can remain unchanged.
                if known_hash is None:
                    other_hashes = {
                        h
                        for (m, p), h in _profile_signature_cache.items()
                        if m == model.lower() and p != int(profile_number)
                    }
                    if after_hash not in other_hashes:
                        _profile_signature_cache[key] = after_hash
                        return True

            time.sleep(0.05)
        except Exception:
            time.sleep(0.05)

    return False


def switch_profile(profile_number):
    if profile_number < 1 or profile_number > 3:
        print("Error: Profile number must be 1-3.")
        return False

    try:
        if not _ensure_service_running():
            print("Error: Could not start/connect ELECOM service.")
            return False

        devices = _list_devices()
        target = _choose_device(devices)
        if not target:
            print("Error: No ELECOM device found via daemon.")
            return False

        model = str(target.get("modelName", "")).lower()
        session = target.get("session")
        if not model or not session:
            print("Error: Device model/session missing in daemon response.")
            return False

        # Primary path for KG-series software profiles:
        # write DB ProfileRawPacket via /write_data so key bindings + lighting switch together.
        if _switch_profile_via_write_data(model, session, profile_number):
            return True

        # Fallback: legacy daemon packet forwarding path.
        # Retry with verification because some device states are flaky.
        for _ in range(3):
            if not _set_current_profile_index(model, session, profile_number):
                continue

            sync_profiles = _get_sync_profiles(model, session)
            profile_packet = _pick_sync_selected_packet(sync_profiles, profile_number)

            # Fallback: if /sync shape is unexpected, use /profile mapping.
            if not profile_packet:
                profiles = _get_profiles(model, session)
                profile_packet = _select_profile_packet(
                    sync_profiles, profiles, profile_number
                )
            if not profile_packet:
                continue

            send_response = _send_message(
                {
                    "schema": "pipe-1.0",
                    "path": f"/{model}/send_profile",
                    "method": 1,
                    "session": session,
                    "content": {"profile_packet": profile_packet},
                }
            )
            if send_response.get("status") != 200:
                continue

            # Verify selected packet stays selected after send.
            verify_sync = _get_sync_profiles(model, session)
            verify_packet = _pick_sync_selected_packet(verify_sync, profile_number)
            if verify_packet and verify_packet == profile_packet:
                return True

            time.sleep(0.05)

        print("Error: switch_profile verification failed after retries.")
        return False

    except Exception as e:
        print(f"An error occurred: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Switch EG Tool Profile (no GUI)")
    parser.add_argument(
        "-p", "--profile", type=int, required=True, help="Profile number (1-3)"
    )
    args = parser.parse_args()
    switch_profile(args.profile)
