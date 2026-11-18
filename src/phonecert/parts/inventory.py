"""Component inventory from the IORegistry (M2 — parts & authenticity).

Everything here is readable over USB with nothing installed on the phone.
Discovered on an iPhone 13 / iOS 26 (see reports/research/<serial>/):

  IOPlatformExpertDevice   serial, MLB serial, model/region (hex-encoded strings)
  AppleAuthCPRelay         battery authentication (AuthPassed, isTrusted, authErrorDescription)
  AppleH13CamIn            camera module serials (Back/SuperWide/Front/FrontIR/Projector) + validation
  ApplePearlSEPDriver      Face ID self test
  AppleCLCD2               display Panel_ID
  AppleHapticsSupportLEAP  Taptic Engine ModuleSerial
  AppleANS3CGv2Controller  NAND model / serial
  AppleMultitouchDevice    Multitouch ID
  AppleCS35L27Amp          speaker amp attached + calibration

Class names carry the chip generation (H13 → H16…), so they are discovered
with CLASS_PATTERNS against the IOService tree instead of hard-coded.
"""
import re

CLASS_PATTERNS = {
    "platform": r"^IOPlatformExpertDevice$",
    "battery_auth": r"^AppleAuthCPRelay$",
    "camera": r"^AppleH\d+CamIn$",
    "face_id": r"^ApplePearlSEPDriver$",
    "display": r"^AppleCLCD2$",
    "taptic": r"^AppleHapticsSupportLEAP$",
    "nand": r"^AppleANS\w*Controller$",
    "touch": r"^AppleMultitouchDevice$",
    "speaker": r"^AppleCS35L\d+Amp$",
}


def find_classes(tree: dict) -> dict:
    """Map each part key to the IORegistry class name present on this device."""
    classes = set()
    stack = [tree]
    while stack:
        node = stack.pop()
        if node.get("className"):
            classes.add(node["className"])
        stack.extend(node.get("children", []))
    found = {}
    for key, pattern in CLASS_PATTERNS.items():
        match = sorted(c for c in classes if re.match(pattern, c))
        if match:
            found[key] = match[0]
    return found


def hexstr(value):
    """IORegistry strings often arrive as {"$hex": "..."}; decode to text, else None."""
    if isinstance(value, dict) and "$hex" in value:
        try:
            return bytes.fromhex(value["$hex"]).decode("ascii").rstrip("\x00") or None
        except (ValueError, UnicodeDecodeError):
            return None
    return value if isinstance(value, str) else None


def _model_config(raw) -> dict:
    """'receiver_1=AAC;wifi_module_vendor=USI;MoPED=0x..' → dict."""
    text = hexstr(raw) or ""
    return dict(item.split("=", 1) for item in text.split(";") if "=" in item)


CAMERAS = {"back": "BackCamera", "back_ultrawide": "BackSuperWideCamera", "back_tele": "BackTeleCamera",
           "front": "FrontCamera", "front_ir": "FrontIRCamera"}


def analyse(props: dict, battery_raw: dict | None = None) -> dict:
    """props: {part key: IORegistry properties dict} as returned by reader.ioregistry_class."""
    p = props.get("platform", {})
    auth = props.get("battery_auth", {})
    cam = props.get("camera", {})
    bat = battery_raw or {}
    bat_data = bat.get("BatteryData", {})

    cameras = {}
    for key, prefix in CAMERAS.items():
        if f"{prefix}Expected" in cam or f"{prefix}ModuleSerialNumString" in cam:
            cameras[key] = {"expected": cam.get(f"{prefix}Expected"),
                            "serial": cam.get(f"{prefix}ModuleSerialNumString") or None}
    panel_id = props.get("display", {}).get("Panel_ID")

    return {
        "logic_board": {
            "serial": hexstr(p.get("serial-number")),
            "mlb_serial": hexstr(p.get("mlb-serial-number")),
            "model_number": hexstr(p.get("model-number")),
            "regulatory_model": hexstr(p.get("regulatory-model-number")),
            "wifi_module_vendor": _model_config(p.get("model-config")).get("wifi_module_vendor"),
            "receiver_vendor": _model_config(p.get("model-config")).get("receiver_1"),
        },
        "battery": {
            "serial": bat.get("Serial") or bat_data.get("Serial"),
            "manufacturer_data": hexstr(bat_data.get("MfgData")),
            "auth_passed": auth.get("AuthPassed"),
            "trusted": auth.get("isTrusted"),
            "auth_status": auth.get("authErrorDescription"),
        },
        "display": {
            "panel_id": panel_id,
            "panel_serial": panel_id.split("+", 1)[0] if panel_id else None,
        },
        "cameras": cameras,
        "camera_validation": {k: v for k, v in cam.items() if k.endswith("ValidationStatus") or k.endswith("DATFileStatus")},
        "face_id": {
            "projector_serial": cam.get("FrontIRStructuredLightProjectorSerialNumString") or None,
            "self_test_result": props.get("face_id", {}).get("PearlSelfTestResult"),
        },
        "taptic": {
            "serial": props.get("taptic", {}).get("ModuleSerial"),
            "firmware": props.get("taptic", {}).get("FirmwareVersion"),
        },
        "nand": {
            "model": props.get("nand", {}).get("Model Number"),
            "serial": props.get("nand", {}).get("Serial Number"),
            "firmware": props.get("nand", {}).get("Firmware Revision"),
        },
        "touch": {"multitouch_id": props.get("touch", {}).get("Multitouch ID"),
                  "critical_errors": props.get("touch", {}).get("Critical Errors"),
                  "critical_errors_total": props.get("touch", {}).get("Critical Errors Accumulator"),
                  "resets": props.get("touch", {}).get("ResetCount")},
        "speaker": {
            "attached": props.get("speaker", {}).get("DeviceAttached"),
            "calibrated": props.get("speaker", {}).get("AmpImonCalibrationSuccess"),
        },
    }


def flags(inv: dict) -> list[str]:
    """Human-readable warnings. Only things we have evidence for; absence of data is reported, not judged."""
    out = []
    b = inv["battery"]
    if b["auth_passed"] is False or b["trusted"] is False:
        out.append(f"Battery failed Apple authentication ({b['auth_status']}) — likely non-genuine or unpaired")
    elif b["auth_passed"] is None:
        out.append("Battery authentication not readable")
    for name, c in inv["cameras"].items():
        if c["expected"] and not c["serial"]:
            out.append(f"Camera {name}: expected but no module serial — missing or unrecognised")
    fid = inv["face_id"]["self_test_result"]
    if fid not in (None, 0):
        out.append(f"Face ID self test returned {fid}")
    if inv["display"]["panel_id"] is None:
        out.append("Display Panel_ID not readable")
    if inv["speaker"]["attached"] is False:
        out.append("Speaker amp reports no device attached")
    t = inv["touch"]
    if (t.get("critical_errors_total") or 0) > 0 or (t.get("resets") or 0) > 0:
        out.append(f"Touch controller logged {t.get('critical_errors_total') or 0} critical errors and "
                   f"{t.get('resets') or 0} resets — watch for ghost touches")
    return out
