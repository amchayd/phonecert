"""Passive hardware presence checks from the IORegistry tree (M5 level 1).

Nothing runs on the phone: we look at which driver nodes exist and whether a
driver matched them (a node with children = the kernel found and initialised
the part). This proves a component is present and talking to iOS, not that it
performs well — the interactive Safari tests cover that.

Discovered on the iPhone 13 (iOS 26): sensors hang under AppleSPU (the always-on
processor) with plain names: accel, gyro, compass, pressure, prox, als, rose (U1
ultra-wideband), ttw (tap to wake). Radios: wlan/AppleBCMWLANCore, bluetooth/
AppleBluetoothModule, stockholm (NFC controller), hammerfest (secure element).
"""
import re

# key → (label, path regex matched against "/…/parent/name", regex matched against className OR node name)
CHECKS = {
    "accelerometer": ("Accelerometer", r"/AppleSPU/accel$", None),
    "gyroscope": ("Gyroscope", r"/AppleSPU/gyro$", None),
    "compass": ("Compass", r"/AppleSPU/compass$", None),
    "barometer": ("Barometer", r"/AppleSPU/pressure$", None),
    "proximity": ("Proximity sensor", r"/AppleSPU/prox$", None),
    "ambient_light": ("Ambient light sensor", r"/AppleSPU/als$", None),
    "uwb": ("Ultra-wideband (U1)", r"/AppleSPU/rose$", None),
    "tap_to_wake": ("Tap to wake", r"/AppleSPU/ttw$", None),
    "multitouch": ("Touch controller", None, r"^AppleMultitouchDevice$"),
    "wifi": ("Wi-Fi", None, r"^AppleBCMWLANCore$"),
    "bluetooth": ("Bluetooth", None, r"^AppleBluetoothModule$"),
    "nfc": ("NFC", None, r"^AppleStockholmControl$"),
    "secure_element": ("Secure element (Apple Pay)", None, r"^AppleHammerfestControl$"),
    "backlight": ("Display backlight", None, r"^AppleARMBacklight$"),
    "audio_codec": ("Audio codec", None, r"^AppleCS42L\d+Audio$"),
    "speaker_amp": ("Speaker amplifier", None, r"^AppleCS35L\d+Amp$"),
    "mic_aop": ("Always-on microphone path", None, r"^AppleAOPAudioLPMicInDevice$"),
    "haptics": ("Taptic Engine driver", None, r"^AppleHapticsSupportLEAP$"),
    "lightning_port": ("Charge port controller", None, r"^AppleCBTL\d+$"),
    "baseband": ("Cellular baseband", None, r"^AppleBasebandM\d+$|^AppleBasebandPCI$"),
    "face_id_sep": ("Face ID secure driver", None, r"^ApplePearlSEPDriver$"),
    "camera_isp": ("Camera ISP", None, r"^AppleH\d+CamIn$"),
}


def _nodes(tree):
    stack = [(tree, "")]
    while stack:
        node, path = stack.pop()
        p = path + "/" + str(node.get("name", "?"))
        yield p, node
        for ch in node.get("children", []):
            stack.append((ch, p))


def analyse(tree: dict) -> dict:
    nodes = list(_nodes(tree))
    out = {}
    for key, (label, path_re, class_re) in CHECKS.items():
        hits = [n for p, n in nodes
                if (path_re and re.search(path_re, p))
                or (class_re and (re.match(class_re, n.get("className") or "") or re.match(class_re, str(n.get("name") or ""))))]
        if not hits:
            out[key] = {"label": label, "status": "missing", "detail": "no driver node in the registry"}
            continue
        initialised = any(n.get("children") for n in hits) or any("registered" in (n.get("state") or "") and "!registered" not in (n.get("state") or "") for n in hits)
        out[key] = {"label": label, "status": "present" if initialised else "found",
                    "detail": hits[0].get("className") or hits[0].get("name"),
                    "count": len(hits)}
    present = sum(1 for v in out.values() if v["status"] == "present")
    return {"checks": out, "present": present, "total": len(out),
            "missing": [k for k, v in out.items() if v["status"] == "missing"]}
