"""What PhoneCert tests on a phone: the catalogue, and how results are counted.

Three kinds of result live in a report under "tests":
  auto    computed by the Mac (from the scan, or because the phone reached the test page)
  web     run on the Safari test page
  manual  ticked by hand in the app's Checklist
"""
from datetime import datetime

WEB_TESTS = {
    "touch": "Touch grid — every cell of the screen responds",
    "touch_rate": "Touch sampling — events per second while dragging",
    "ghost_touch": "Ghost touches — none in 10 s without touching",
    "multitouch": "Multi-touch — five fingers at once",
    "display": "Display — colours, grey and gradient: no dead pixels, marks or burn-in",
    "speaker": "Speakers — tone and 100 Hz–10 kHz sweep, no rattle",
    "vibration": "Haptics — felt the taps",
    "wifi_speed": "Wi-Fi throughput — download from the Mac",
    "battery_load": "Battery under load — voltage sag while the phone works hard",
    # Only reachable on the HTTPS page (Safari secure context):
    "camera": "Cameras — front and rear preview in the browser",
    "microphone": "Microphone — level meter reacts",
    "motion": "Motion sensors — accelerometer and gyroscope move",
    "location": "GPS — a position fix",
}
SECURE_ONLY = {"camera", "microphone", "motion", "location"}
# The page cannot measure these: the tester looks / listens / feels and taps pass or fail.
# Every other page test decides its own result.
JUDGED_BY_YOU = {"display", "speaker", "vibration", "camera", "microphone"}
# Results the Mac records on its own, no tap needed.
AUTO_TESTS = {
    "charging": "Charging over the cable during the scan",
    "touch_controller": "Touch controller error counters",
    "wifi": "Wi-Fi — the phone reached the Mac's test page",
}
MANUAL_TESTS = {
    "buttons": "Buttons — power, volume up/down, mute switch / action button",
    "face_id": "Face ID — unlock works, attention detection on",
    "true_tone": "True Tone toggle present in Settings → Display (missing = non-original screen)",
    "cameras": "Cameras — rear, ultrawide, front: photo sharp, no spots, flash works",
    "earpiece": "Earpiece and top mic — a call off speakerphone is clear both ways",
    "cellular": "Cellular — call and data with your SIM",
    "bluetooth": "Bluetooth pairs",
    "nfc": "Apple Pay / NFC — the tap sheet appears (double-click side button)",
    "water_indicator": "Liquid contact indicator in the SIM tray is white, not red",
    "body": "Body — no cracks, bends or deep scratches",
}

WEB_RESULT_STATUSES = ("pass", "fail")


def summary(tests: dict | None) -> dict:
    tests = tests or {}
    web, manual, auto = tests.get("web", {}), tests.get("manual", {}), tests.get("auto", {})
    done = len(web) + len(manual) + len(auto)
    failed = [k for d in (web, manual, auto) for k, v in d.items() if v.get("status") == "fail"]
    return {"done": done, "total": len(WEB_TESTS) + len(MANUAL_TESTS) + len(AUTO_TESTS), "failed": failed}


def auto_from_scan(report: dict) -> dict:
    """Automatic results computed from scan data (charging, touch controller). Stored as tests.auto."""
    out = {}
    ch = (report.get("battery") or {}).get("charging") or {}
    if ch.get("status") in ("pass", "fail"):
        w = f", {ch['adapter_watts']} W adapter" if ch.get("adapter_watts") else ""
        detail = (f"charging at {ch.get('current_ma')} mA{w}" if ch["status"] == "pass"
                  else f"cable connected but not charging (reason {ch.get('not_charging_reason')})")
        out["charging"] = {"status": ch["status"], "details": {"summary": detail}, "note": None,
                           "at": datetime.now().isoformat(timespec="seconds")}
    t = ((report.get("parts") or {}).get("touch") or {})
    if t.get("critical_errors_total") is not None or t.get("resets") is not None:
        errs, resets = t.get("critical_errors_total") or 0, t.get("resets") or 0
        out["touch_controller"] = {"status": "fail" if errs or resets else "pass",
                                   "details": {"critical_errors": errs, "resets": resets}, "note": None,
                                   "at": datetime.now().isoformat(timespec="seconds")}
    return out
