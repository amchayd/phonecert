"""SIM, carrier and radio identity from `lockdown info`.

Lockdown describes two slots: slot 1 via SIMStatus / IntegratedCircuitCardIdentity /
InternationalMobileSubscriberIdentity, slot 2 via the same keys suffixed "2".
SIMStatus only covers slot 1 — on the test iPhone 13 the only SIM (a physical card)
sits in slot 2, so slot 1 says "not inserted" while the phone has full service.
SIMTrayStatus describes the physical tray whichever slot the card is registered on.

Personal identifiers (ICCID, IMSI, phone number) stay in the raw section only;
here they are reduced to "present" booleans.
"""

SIM_STATUS = {
    "kCTSIMSupportSIMStatusReady": "Ready",
    "kCTSIMSupportSIMStatusNotInserted": "Empty",
    "kCTSIMSupportSIMStatusPINRequired": "PIN required",
    "kCTSIMSupportSIMStatusPINLocked": "PIN locked",
    "kCTSIMSupportSIMStatusPUKRequired": "PUK required",
    "kCTSIMSupportSIMStatusPUKLocked": "PUK locked",
    "kCTSIMSupportSIMStatusFailure": "SIM failure",
}
_NO_SIM = {None, "", "kCTSIMSupportSIMStatusNotInserted"}


def _status_text(code):
    """Known code → label; unknown code → 'kCTSIMSupportSIMStatusFooBar' → 'Foo bar'."""
    if code in SIM_STATUS:
        return SIM_STATUS[code]
    if not code:
        return None
    import re
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", code.removeprefix("kCTSIMSupportSIMStatus"))
    return words[:1].upper() + words[1:].lower()
TRAY_STATUS = {
    "kCTSIMSupportSIMTrayInsertedWithSIM": "Tray in, SIM card present",
    "kCTSIMSupportSIMTrayInsertedNoSIM": "Tray in, empty",
    "kCTSIMSupportSIMTrayAbsent": "Tray absent",
}


def _carrier(bundle_id):
    # "com.apple.Example_xx" → "Example (xx)"
    name = (bundle_id or "").removeprefix("com.apple.")
    if "_" in name:
        carrier, country = name.rsplit("_", 1)
        return f"{carrier} ({country})"
    return name or None


def _slot(info: dict, n: int, bundles: list) -> dict:
    sfx = "" if n == 1 else "2"
    present = bool(info.get(f"IntegratedCircuitCardIdentity{sfx}") or info.get(f"InternationalMobileSubscriberIdentity{sfx}"))
    status = info.get("SIMStatus") if n == 1 else None
    bundle = next((b for b in bundles if (b.get("Slot") or "").removeprefix("k").lower() in ({"one"}, {"two"})[n - 1]), None)
    return {
        "slot": n,
        # slot 1: any status other than "not inserted" means a card is there (ready, PIN-locked, PUK…)
        "present": present or (n == 1 and status not in _NO_SIM),
        "embedded": info.get(f"SIM{n}IsEmbedded"),
        "status": _status_text(status),   # lockdown only reports slot 1
        "carrier": _carrier(bundle.get("CFBundleIdentifier")) if bundle else None,
        "mcc": bundle.get("MCC") if bundle else None,
        "mnc": bundle.get("MNC") if bundle else None,
    }


def analyse(info: dict) -> dict:
    bundles = [b for b in (info.get("CarrierBundleInfoArray") or []) if isinstance(b, dict)]
    slots = [_slot(info, 1, bundles), _slot(info, 2, bundles)]
    active = [s for s in slots if s["present"]]
    if active:
        summary = ", ".join(f"{'eSIM' if s['embedded'] else 'physical SIM'} in slot {s['slot']}"
                            + (f" ({s['carrier']})" if s["carrier"] else "") for s in active)
    else:
        summary = "No SIM"
    tray = info.get("SIMTrayStatus")
    # A card in the tray but no slot registering it → reader / card problem worth a look.
    tray_has_card = tray == "kCTSIMSupportSIMTrayInsertedWithSIM"
    physical_active = any(s["present"] and not s["embedded"] for s in slots)
    return {
        "summary": summary,
        "active_count": len(active),
        "slots": slots,
        "tray": TRAY_STATUS.get(tray, tray),
        "esim": any(s["present"] and s["embedded"] for s in slots),
        "card_not_recognised": tray_has_card and not physical_active,
        "telephony": info.get("TelephonyCapability"),
        "baseband_version": info.get("BasebandVersion"),
        "activation": info.get("ActivationState"),
    }
