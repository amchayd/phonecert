"""Trust: can this phone be bought safely?

The deal-breakers a used-iPhone buyer gets burned by, ordered by damage:
  1. Activation Lock (Find My still on)      → phone unusable after erase
  2. Blacklisted IMEI (stolen / unpaid)      → no network, ever          (needs M4 API)
  3. Supervised / MDM                        → a company can wipe or restrict it remotely
  4. Carrier (SIM) lock                      → only one network           (manual / M4)
  5. Jailbreak, non-genuine parts, replacement/refurb unit → price, not safety

Each check: status pass | fail | warn | unknown | manual | not_checked,
severity blocker | warning | info. Verdict: blocked / warnings / clear / incomplete.
"""

UNIT_TYPE_NOTE = {
    "Apple refurbished": "Refurbished by Apple — fine, but not a new-retail unit.",
    "Replacement unit": "Replacement unit issued by Apple service — the serial is not the one on the original box.",
    "Personalised": "Personalised (engraved) unit.",
}


def _check(key, title, status, severity, detail, action=None):
    return {"key": key, "title": title, "status": status, "severity": severity, "detail": detail, "action": action}


def _usable(imei_check: dict | None) -> dict | None:
    """The IMEI lookup result, or None when there is none or it failed."""
    return imei_check if imei_check and "error" not in imei_check else None


def _with_lookup_button(check: dict, lookup: dict, device: dict, runnable: bool = True) -> dict:
    """Tell the UI this check can be answered by the paid IMEI lookup (the Trust tab shows "Run check")."""
    check["runnable"] = runnable and bool(lookup.get("available")) and bool(device.get("imei"))
    check["cost_usd"] = lookup.get("cost_usd")
    check["provider"] = lookup.get("provider")
    return check


# ---- one function per check; each returns a check dict ----

def _find_my(find_my) -> dict:
    """1. Activation Lock."""
    title = "Find My / Activation Lock"
    if not isinstance(find_my, bool):
        return _check("find_my", title, "unknown", "blocker",
                      f"Could not read ({find_my.get('error') if isinstance(find_my, dict) else 'no data'}).",
                      "After an erase, the Hello screen shows whether a previous owner's Apple ID is required.")
    if find_my:
        return _check("find_my", title, "fail", "blocker",
                      "Find My is ON: the phone is linked to an Apple ID. After an erase it will ask for that owner's password.",
                      "Signing out of iCloud (Settings → [name] → Sign Out) turns it off. A re-scan then reads OFF.")
    return _check("find_my", title, "pass", "blocker",
                  "Find My is OFF: no Apple ID is linked. The phone can be set up by a new owner.")


def _blacklist(imei_check: dict | None, lookup: dict, device: dict) -> dict:
    """2. Blacklist: from the IMEI provider when a lookup was run."""
    title = "IMEI blacklist (stolen / lost / unpaid)"
    ic = _usable(imei_check)
    if ic:
        bl = ic["blacklist"]
        src = f"{ic['provider']} service {ic['service']}, {ic['checked_at'][:10]}{' (cached)' if ic.get('cached') else ''}"
        text = {"pass": f"GSMA blacklist: clean ({bl.get('detail')}).", "fail": f"BLACKLISTED: {bl.get('detail')}.",
                "unknown": f"Provider answered but no blacklist field recognised ({bl.get('detail')})."}[bl["status"]]
        return _check("blacklist", title, bl["status"], "blocker", f"{text} Source: {src}.",
                      None if bl["status"] == "pass" else "A blacklisted IMEI gets no network on any carrier and cannot be cleared by the buyer.")
    if imei_check:                       # a lookup was run and failed
        why, action = f"lookup failed: {imei_check['error']}", "Try again, or check the IMEI on a web checker."
    elif lookup.get("available"):
        why, action = "paid lookup not run yet", None
    else:
        why = lookup.get("reason") or "no IMEI provider configured: add a key in Settings"
        action = f"IMEI {device.get('imei') or '?'}: use a web blacklist checker."
    return _with_lookup_button(_check("blacklist", title, "not_checked", "blocker", f"Not checked — {why}.", action), lookup, device)


def _supervision(cloud_config: dict) -> dict:
    """3a. Supervision (company-owned)."""
    title = "Supervision (company-owned)"
    if "error" in (cloud_config or {}):
        return _check("supervision", title, "unknown", "blocker", f"Could not read ({cloud_config['error']}).")
    if cloud_config.get("IsSupervised"):
        return _check("supervision", title, "fail", "blocker",
                      "The phone is supervised: an organisation enrolled it (DEP/ABM). It re-enrols after every erase.",
                      "Walk away unless the organisation releases it from Apple Business Manager.")
    return _check("supervision", title, "pass", "blocker", "Not supervised.")


def _mdm(profiles: dict) -> dict:
    """3b. Configuration profiles / MDM."""
    title = "Configuration profiles / MDM"
    if "error" in (profiles or {}):
        return _check("mdm", title, "unknown", "blocker", f"Could not read ({profiles['error']}).")
    if profiles.get("mdm_enrolled"):
        return _check("mdm", title, "fail", "blocker",
                      f"MDM profile installed: {', '.join(profiles.get('profiles', []))}. A third party can lock, wipe or monitor it.",
                      "Removable under Settings → General → VPN & Device Management; a re-scan confirms.")
    if profiles.get("count"):
        return _check("mdm", title, "warn", "warning",
                      f"{profiles['count']} configuration profile(s): {', '.join(profiles.get('profiles', []))}.",
                      "Removable under Settings → General → VPN & Device Management.")
    return _check("mdm", title, "pass", "blocker", "No configuration profiles.")


def _carrier_lock(imei_check: dict | None, lookup: dict, device: dict) -> dict:
    """4. Carrier lock: not readable over USB; from the IMEI provider, else a manual check."""
    title = "Carrier (SIM) lock"
    ic = _usable(imei_check)
    if ic and ic["carrier_lock"]["status"] != "unknown":
        cl = ic["carrier_lock"]
        return _check("carrier_lock", title, cl["status"], "warning",
                      f"{'Locked' if cl['status'] == 'fail' else 'Unlocked'}: {cl.get('detail')}"
                      + (f" · carrier {cl['carrier']}" if cl.get("carrier") else "") + f" (source: {ic['provider']}).",
                      "Only the original carrier can unlock it." if cl["status"] == "fail" else None)
    check = _check("carrier_lock", title, "manual", "warning",
                   "Not readable over USB" + (f"; provider gave no lock field ({ic['carrier_lock'].get('detail')})" if ic else "") + ".",
                   "Settings → General → About → Carrier Lock must say “No SIM restrictions”, or test your own SIM.")
    return _with_lookup_button(check, lookup, device, runnable=ic is None)


def _activation(device: dict) -> dict:
    """5. Activation state."""
    state = device.get("activation_state")
    return _check("activation", "Activation", "pass" if state == "Activated" else "warn", "warning",
                  f"Activation state: {state or 'unknown'}.",
                  None if state == "Activated" else "An unactivated phone needs a network and a clean Activation Lock to activate.")


def _setup(setup: dict) -> dict:
    """6. Account / data still on the phone."""
    title = "Erased / set-up state"
    setup_state = (setup or {}).get("SetupState")
    if "error" in (setup or {}):
        return _check("setup", title, "unknown", "info", f"Could not read ({setup['error']}).")
    if setup_state:
        return _check("setup", title, "warn", "info",
                      f"The phone is set up ({setup_state}, {setup.get('RestoreState')}): it holds the seller's data and account.",
                      "Settings → General → Transfer or Reset → Erase All Content and Settings removes it.")
    return _check("setup", title, "pass", "info", "Not set up (Hello screen).")


def _jailbreak(jailbreak: dict) -> dict:
    """7. Jailbreak."""
    verdict = (jailbreak or {}).get("verdict")
    status = {"none": "pass", "suspicious": "warn", "likely": "fail"}.get(verdict, "unknown")
    detail = {"none": "No jailbreak signs.",
              "suspicious": "Dev-signed apps present — common for developers, also for jailbreak tooling.",
              "likely": "Jailbreak tooling detected."}.get(verdict, "Could not read.")
    return _check("jailbreak", "Jailbreak", status, "warning", detail,
                  "An erase + iOS restore removes a jailbreak." if status != "pass" else None)


def _unit_type(device: dict) -> dict:
    """8. Unit type (refurb / replacement)."""
    unit = device.get("unit_type")
    status = "pass" if unit == "New retail" else "warn" if unit in UNIT_TYPE_NOTE else "unknown"
    fallback = f"{unit}: new retail unit." if unit == "New retail" else f"Model number prefix unknown ({unit})."
    return _check("unit_type", "Unit type", status, "info", UNIT_TYPE_NOTE.get(unit, fallback))


def _parts(parts: dict | None) -> dict | None:
    """9. Parts (summary of the Parts tab). No check when the parts could not be read."""
    if not parts or "error" in parts:
        return None
    bd = parts.get("build_dates") or {}
    flagged = (parts.get("flags") or []) + bd.get("reasons", []) + ((parts.get("battery_age") or {}).get("reasons") or [])
    return _check("parts", "Genuine parts", "warn" if flagged else "pass", "warning",
                  "; ".join(flagged) if flagged else f"Battery authenticated, parts {bd.get('verdict', 'n/a')}.",
                  "Compare with Settings → General → About → Parts and Service History." if flagged else None)


def _stolen_device_protection() -> dict:
    """10. Stolen Device Protection: purely advisory."""
    return _check("sdp", "Stolen Device Protection (iOS 17.3+)", "manual", "info",
                  "If the seller has it on, turning off Find My may require a 1-hour delay away from familiar locations.",
                  "Signing out takes effect faster when done at a familiar location.")


def _verdict(checks: list[dict]) -> dict:
    """blocked > warnings > incomplete > clear, with the keys behind each."""
    blockers = [c for c in checks if c["severity"] == "blocker" and c["status"] == "fail"]
    warnings = [c for c in checks if c["status"] in ("warn", "fail") and c not in blockers]
    unchecked = [c for c in checks if c["severity"] == "blocker" and c["status"] in ("unknown", "not_checked")]
    verdict = "blocked" if blockers else "warnings" if warnings else "incomplete" if unchecked else "clear"
    return {"verdict": verdict, "blockers": [c["key"] for c in blockers], "warnings": [c["key"] for c in warnings],
            "unchecked": [c["key"] for c in unchecked]}


def analyse(*, find_my, cloud_config: dict, setup: dict, profiles: dict, jailbreak: dict,
            device: dict, parts: dict | None = None, imei_check: dict | None = None,
            imei_lookup: dict | None = None) -> dict:
    """imei_lookup: {"available": bool, "provider": str|None, "services": [..], "cost_usd": float|None}
    describes the paid lookup the UI can trigger when imei_check is absent."""
    lookup = imei_lookup or {}
    checks = [                       # in the order a buyer should read them
        _find_my(find_my),
        _blacklist(imei_check, lookup, device),
        _supervision(cloud_config),
        _mdm(profiles),
        _carrier_lock(imei_check, lookup, device),
        _activation(device),
        _setup(setup),
        _jailbreak(jailbreak),
        _unit_type(device),
        _parts(parts),
        _stolen_device_protection(),
    ]
    checks = [c for c in checks if c is not None]
    return {**_verdict(checks), "checks": checks}
