import os
import sys
import hmac
import hashlib
import base64
import json
import time
import uuid
import platform
from datetime import datetime

SECRET_SALT = b"AI_LASER_SCANNER_SECURE_SALT_v1_2026_TRADING_PRO"

def get_base_dir():
    """Returns the persistent folder for writable files like license.lic."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_license_file():
    return os.path.join(get_base_dir(), "license.lic")

def get_machine_id():
    """Generates a unique and consistent Hardware ID for this PC."""
    unique_parts = []
    
    # 1. Windows Machine GUID
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        unique_parts.append(str(guid))
    except Exception:
        pass

    # 2. System UUID / Node
    try:
        unique_parts.append(str(uuid.getnode()))
    except Exception:
        pass

    # 3. Platform & Processor
    unique_parts.append(str(platform.node()))
    unique_parts.append(str(platform.processor()))

    raw_str = "|".join(unique_parts)
    digest = hashlib.sha256(raw_str.encode('utf-8')).hexdigest().upper()
    return f"{digest[:4]}-{digest[4:8]}-{digest[8:12]}"

def generate_license_key(machine_id, days_valid=0):
    """
    Generates a cryptographically signed license key bound to a machine ID.
    days_valid = 0 means LIFETIME.
    """
    machine_id = machine_id.strip().upper()
    now_ts = int(time.time())
    if days_valid > 0:
        expiry_ts = now_ts + (days_valid * 86400)
    else:
        expiry_ts = 0  # Lifetime

    payload = {
        "m": machine_id,
        "e": expiry_ts
    }
    payload_json = json.dumps(payload, separators=(',', ':'))
    b64_payload = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8').rstrip('=')

    sig = hmac.new(SECRET_SALT, b64_payload.encode('utf-8'), hashlib.sha256).hexdigest()[:12].upper()
    return f"AILS-{sig}-{b64_payload}"

def validate_license_key(key_str, current_machine_id=None):
    """
    Validates a license key against the local machine ID and expiration.
    Returns: (bool is_valid, str message, str expiry_info)
    """
    if not key_str:
        return False, "কোনো লাইসেন্স কি দেওয়া হয়নি (No key entered)", ""

    key_str = key_str.strip()
    parts = key_str.split('-')
    if len(parts) < 3 or parts[0] != "AILS":
        return False, "ভুল লাইসেন্স কি ফরম্যাট (Invalid key format)", ""

    sig = parts[1]
    b64_payload = "-".join(parts[2:])

    expected_sig = hmac.new(SECRET_SALT, b64_payload.encode('utf-8'), hashlib.sha256).hexdigest()[:12].upper()
    if not hmac.compare_digest(sig, expected_sig):
        return False, "অবৈধ বা নকল লাইসেন্স কি (Invalid signature)", ""

    try:
        padded = b64_payload + "=" * ((4 - len(b64_payload) % 4) % 4)
        payload_bytes = base64.urlsafe_b64decode(padded)
        payload = json.loads(payload_bytes.decode('utf-8'))
    except Exception:
        return False, "লাইসেন্স ডাটা পড়া যায়নি (Corrupt payload)", ""

    key_machine_id = payload.get("m", "")
    expiry_ts = payload.get("e", 0)

    if current_machine_id is None:
        current_machine_id = get_machine_id()

    if key_machine_id != "UNIVERSAL" and key_machine_id != current_machine_id.strip().upper():
        return False, f"এই কি-টি অন্য ডিভাইসের জন্য তৈরি (HWID mismatch: {key_machine_id})", ""

    if expiry_ts > 0:
        now_ts = int(time.time())
        if now_ts > expiry_ts:
            exp_date = datetime.fromtimestamp(expiry_ts).strftime("%Y-%m-%d")
            return False, f"লাইসেন্সের মেয়াদ শেষ হয়ে গেছে ({exp_date})", ""
        else:
            exp_date = datetime.fromtimestamp(expiry_ts).strftime("%d %b %Y, %I:%M %p")
            return True, "লাইসেন্স সফলভাবে সক্রিয় হয়েছে!", f"মেয়াদ: {exp_date} পর্যন্ত"
    else:
        return True, "লাইসেন্স সফলভাবে সক্রিয় হয়েছে!", "মেয়াদ: আজীবন (Lifetime Access)"

def is_activated():
    """Checks if the app is currently activated on this PC."""
    lic_path = get_license_file()
    if not os.path.exists(lic_path):
        return False, "সক্রিয় নয় (Not Activated)"
    try:
        with open(lic_path, "r", encoding="utf-8") as f:
            key_str = f.read().strip()
        is_val, msg, exp_info = validate_license_key(key_str)
        return is_val, exp_info if is_val else msg
    except Exception as e:
        return False, str(e)

def save_license(key_str):
    """Saves the license key to disk next to executable."""
    lic_path = get_license_file()
    with open(lic_path, "w", encoding="utf-8") as f:
        f.write(key_str.strip())
