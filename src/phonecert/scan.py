"""Scanning a phone: read everything the device exposes, analyse it, assemble the report.

`scan()` is the one entry point; the analysers it calls are pure functions in battery/, parts/,
system/ and checks/, each fed with what a reader in device/reader.py returned.
"""
import os
import re
import subprocess
from datetime import datetime

from phonecert.battery import health
from phonecert.checks import catalog
from phonecert.checks import imei as imei_check
from phonecert.device.models import model_name, release_year
from phonecert.device.reader import (DeviceError, battery_info, cloud_configuration, crash_files,
                                     disk_usage, find_my_associated, installed_apps,
                                     installed_profiles, ioregistry_class, ioregistry_tree,
                                     list_devices, lockdown_info, setup_state)
from phonecert.parts import battery_age, build_dates, inventory, sensors
from phonecert.report import store
from phonecert.system import jailbreak, panics, profiles, sim, storage, trust

UNIT_TYPES = {"M": "New retail", "F": "Apple refurbished", "N": "Replacement unit", "P": "Personalised"}

DEVICE_FIELDS = {
    "name": "DeviceName",
    "product_type": "ProductType",      # e.g. iPhone14,5
    "model_number": "ModelNumber",      # e.g. MLPF3  (M=new, F=refurb, N=replacement)
    "region": "RegionInfo",             # e.g. ZD/A
    "color": "DeviceColor",
    "serial": "SerialNumber",
    "imei": "InternationalMobileEquipmentIdentity",
    "imei2": "InternationalMobileEquipmentIdentity2",
    "ios_version": "ProductVersion",
    "activation_state": "ActivationState",
    "locked_now": "PasswordProtected",   # current lock state, NOT "has a passcode" (flips when unlocked)
    "wifi_mac": "WiFiAddress",
    "bluetooth_mac": "BluetoothAddress",
    "timezone": "TimeZone",
    "build_version": "BuildVersion",
    "hardware_model": "HardwareModel",
}


def _read(reader, analyser, default):
    """Call a device reader; return (raw, analysed) or (default, {"error": ...})."""
    try:
        raw = reader()
    except (DeviceError, subprocess.TimeoutExpired) as e:
        return default, {"error": str(e) or "timeout"}
    return raw, analyser(raw)


# Keys worth keeping in the report's raw section (the full app list is huge).
APP_KEYS = ("CFBundleDisplayName", "CFBundleShortVersionString", "SignerIdentity", "ApplicationType")


def _trim_apps(apps: dict) -> dict:
    return {bid: {k: v for k, v in info.items() if k in APP_KEYS} for bid, info in apps.items()}


# IORegistry keys worth keeping in raw (drop kext boilerplate and big blobs).
_IOREG_SKIP = re.compile(r"^(IO[A-Z]|CFBundle|children$|Elements$|InputReportElements$|ReportDescriptor$"
                         r"|DeviceUsagePairs$|CodecRegister|backlight-|Savage|Signature$|DeviceNonce$)")


def read_parts() -> tuple[dict, dict, dict]:
    """Discover part classes on this device and read their properties. Returns (raw props, classes, tree)."""
    tree = ioregistry_tree()
    classes = inventory.find_classes(tree)
    props = {}
    for key, io_class in classes.items():
        try:
            full = ioregistry_class(io_class)
        except (DeviceError, subprocess.TimeoutExpired) as e:
            props[key] = {"error": str(e) or "timeout"}
            continue
        props[key] = {k: v for k, v in full.items() if not _IOREG_SKIP.match(k)}
    return props, classes, tree


def imei_lookup_info() -> dict:
    """What a paid IMEI lookup would be, for the Trust tab's button."""
    provider = imei_check.provider_from_env()
    services = imei_check.default_services(provider) if provider else []
    reason = (None if provider and services
              else "no IMEI provider key: add one in Settings (or .env, see .env.example)" if not provider
              else "no service ids: set PHONECERT_IMEIINFO_SERVICES=27,8 in .env")
    return {"available": bool(provider and services), "provider": getattr(provider, "name", None),
            "services": services, "cost_usd": imei_check.estimated_cost(provider, services) if provider else None,
            "reason": reason}


def run_imei_lookup(imei: str, services: list[int] | None = None, force: bool = False) -> dict:
    """Paid lookup → merged result, or {"error": …}. Never raises."""
    provider = imei_check.provider_from_env()
    if provider is None:
        return {"error": "no IMEI provider configured"}
    services = services or imei_check.default_services(provider)
    if not services:
        return {"error": "no service ids configured (PHONECERT_IMEIINFO_SERVICES)"}
    try:
        return imei_check.check_imei_multi(imei, provider, services, force=force)
    except imei_check.ImeiError as e:
        return {"error": str(e)}


def build_trust(report: dict, imei_result: dict | None) -> dict:
    """Run the trust analysis of a report with (or without) an IMEI lookup result."""
    raw = report["raw"]
    return trust.analyse(find_my=raw.get("find_my"), cloud_config=raw.get("cloud_configuration") or {},
                         setup=raw.get("setup") or {}, profiles=report["system"].get("profiles") or {},
                         jailbreak=report["system"].get("jailbreak") or {}, device=report["device"],
                         parts=report.get("parts"), imei_check=imei_result, imei_lookup=imei_lookup_info())


def read_device(info: dict) -> dict:
    """Identity fields from lockdown, plus the commercial name and what kind of unit it is."""
    device = {k: info.get(v) for k, v in DEVICE_FIELDS.items()}
    device["model"] = model_name(device.get("product_type"))
    device["unit_type"] = UNIT_TYPES.get((device.get("model_number") or "?")[:1], "Unknown")
    return device


def analyse_parts(raw: dict, info: dict, device: dict, battery: dict) -> dict:
    """Parts inventory with sensors, flags, battery age and build dates. Stores the IORegistry dump in raw."""
    try:
        raw["ioreg"], classes, tree = read_parts()
    except (DeviceError, subprocess.TimeoutExpired) as e:
        return {"error": str(e) or "timeout"}
    parts = inventory.analyse(raw["ioreg"], raw["battery"])
    parts["sensors"] = sensors.analyse(tree)
    parts["flags"] = inventory.flags(parts)
    parts["io_classes"] = classes
    year = release_year(device.get("product_type"))
    board_date = battery_age.mlb_build_date(parts["logic_board"]["mlb_serial"] or info.get("MLBSerialNumber"), year)
    parts["battery_age"] = battery_age.assess(
        battery.get("operating_hours"), board_date,
        battery_age.battery_build_date(parts["battery"]["serial"], year))
    parts["build_dates"] = build_dates.assess(parts, board_date, year)
    return parts


def scan(save: bool = True, imei_mock: bool = False, imei_lookup: bool = False) -> dict:
    info = lockdown_info()
    device = read_device(info)

    # Each extra reader is independent: one failing service must not kill the scan.
    raw = {"lockdown": info}
    raw["battery"], battery = _read(battery_info, health.analyse, default={})
    raw["disk_usage"], disk = _read(disk_usage, storage.analyse, default={})
    raw["crash_files"], panic = _read(crash_files, panics.analyse, default=[])
    raw["profiles"], prof = _read(installed_profiles, profiles.analyse, default={})
    raw["find_my"], _ = _read(find_my_associated, lambda v: v, default=None)
    raw["cloud_configuration"], _ = _read(cloud_configuration, lambda v: v, default={})
    raw["setup"], _ = _read(setup_state, lambda v: v, default={})
    raw["apps"], apps = _read(installed_apps, _trim_apps, default={})
    if "error" in apps:
        jb = {"error": apps["error"]}
    else:
        raw["apps"] = apps
        jb = jailbreak.analyse(apps, raw["crash_files"])

    report = {"scanned_at": datetime.now().isoformat(timespec="seconds"),
              "device": device, "battery": battery, "storage": disk,
              "sim": sim.analyse(info),
              "system": {"panic_logs": panic, "jailbreak": jb, "profiles": prof},
              "parts": analyse_parts(raw, info, device, battery),
              "raw": raw}
    # Paid IMEI lookup only on request (--imei / --imei-mock); otherwise the Trust tab offers a button.
    report["imei_check"] = None
    if imei_lookup or imei_mock:
        if imei_mock:
            os.environ["PHONECERT_IMEI_MOCK"] = "1"
        report["imei_check"] = run_imei_lookup(device["imei"]) if device.get("imei") else {"error": "no IMEI"}
    report["trust"] = build_trust(report, report["imei_check"])
    report["tests"] = {"web": {}, "manual": {}, "auto": catalog.auto_from_scan(report)}
    if save:
        report["saved_to"] = str(store.save_scan(report))
    return report


def devices() -> list[dict]:
    """Connected iPhones with their commercial name, for the UI's Connect screen."""
    return [{"udid": d.get("Identifier"), "name": d.get("DeviceName"),
             "product_type": d.get("ProductType"), "model": model_name(d.get("ProductType")),
             "ios_version": d.get("ProductVersion"), "connection": d.get("ConnectionType")}
            for d in list_devices()]
