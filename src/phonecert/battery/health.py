"""Battery health computation and grading.

Key names differ across iPhone models / iOS versions (newer devices nest
values under e.g. "BatteryData"), so we search the whole structure.
"""


from datetime import datetime

# A shutdown with at least this much charge left is "unexpected" (battery can't hold load).
UNEXPECTED_SHUTDOWN_MIN_PCT = 10


def _find(data, *keys):
    """Return the first non-empty value for any of `keys`, searching nested dicts."""
    if isinstance(data, dict):
        for k in keys:
            v = data.get(k)
            if v not in (None, "", 0):
                return v
        for v in data.values():
            found = _find(v, *keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find(item, *keys)
            if found is not None:
                return found
    return None


def grade(health_pct):
    if health_pct is None:
        return "Unknown"
    if health_pct >= 100:
        return "Excellent"
    if health_pct >= 90:
        return "Good"
    if health_pct >= 80:
        return "Average"
    return "Poor"


def lifetime(raw: dict) -> dict:
    """Gas-gauge lifetime extremes (BatteryData/LifetimeData). Not exposed on iOS 27 / iPhone 16 Pro.

    Units seen on the iPhone 13: Max/MinTemperature in 0.1 °C (514 → 51.4 °C), AverageTemperature
    in °C, capacities in mAh. ResetCnt > 0 means the gauge was reset (battery swap / tampering).
    """
    lt = _find(raw, "LifetimeData")
    if not isinstance(lt, dict) or not lt:
        return {}
    tenth = lambda v: round(v / 10, 1) if isinstance(v, (int, float)) else None
    return {
        "max_temperature_c": tenth(lt.get("MaximumTemperature")),
        "min_temperature_c": tenth(lt.get("MinimumTemperature")),
        "avg_temperature_c": lt.get("AverageTemperature"),
        "max_full_charge_mah": lt.get("MaximumFCC"),
        "min_full_charge_mah": lt.get("MinimumFCC"),
        "max_pack_voltage_mv": lt.get("MaximumPackVoltage"),
        "gauge_resets": lt.get("ResetCnt"),
        "operating_hours": lt.get("TotalOperatingTime"),
    }


def last_shutdown(raw: dict) -> dict:
    """What the battery looked like at the last shutdown (BatteryShutdownReason).

    UISoc 0 at ~3.2 V is a normal empty-battery shutdown. A shutdown with charge left
    (UISoc well above 0) is the classic weak-battery / board-fault symptom.
    """
    sd = raw.get("BatteryShutdownReason") or {}
    if not sd:
        return {}
    ts = sd.get("ShutDownTimestamp")
    soc = sd.get("ShutDownUISoc")
    temp = sd.get("ShutDownTemperature")
    return {
        "at": datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else None,
        "charge_pct": soc,
        "voltage_mv": sd.get("ShutDownVoltage"),
        "temperature_c": round(temp / 100, 1) if isinstance(temp, (int, float)) else None,
        "unexpected": soc is not None and soc >= UNEXPECTED_SHUTDOWN_MIN_PCT,
    }


def charging(raw: dict) -> dict:
    """Is the phone charging over the cable right now? Proves port + charging circuit while scanning.

    Keys (iPhone 13): IsCharging, ExternalConnected, Amperage (mA, > 0 while charging), AdapterDetails
    {Watts, Description}, ChargerData {ChargingCurrent, NotChargingReason}, FullyCharged.
    """
    adapter = raw.get("AdapterDetails") or {}
    charger = raw.get("ChargerData") or {}
    connected = raw.get("ExternalConnected")
    is_charging = raw.get("IsCharging")
    full = raw.get("FullyCharged")
    amps = raw.get("Amperage")
    if connected is None and is_charging is None:
        return {}
    if is_charging or full:
        status = "pass"
    elif connected:
        status = "fail"      # cable detected but no charge → port / charger / battery
    else:
        status = "unknown"   # not plugged in (scan over Wi-Fi?)
    return {
        "status": status,
        "connected": connected,
        "is_charging": is_charging,
        "fully_charged": full,
        "current_ma": amps,
        "adapter_watts": adapter.get("Watts"),
        "adapter": adapter.get("Description"),
        "not_charging_reason": charger.get("NotChargingReason"),
    }


# Above this the battery's internal resistance counts as high. Provisional: the only reference so far is the
# test iPhone 13 (75 % health, iOS says "Service"), whose gauge reports 153 mΩ. Calibrate with a healthy phone.
RESISTANCE_HIGH_MOHM = 150


def resistance(raw: dict) -> dict:
    """The battery's internal resistance as its own gauge tracks it (BatteryData.WeightedRa, mΩ).

    High resistance is what makes an aged battery sag and shut down under load even when the health %
    still looks acceptable. The gauge learns it over the battery's life, so it reads the same at any
    charge level, on or off the charger. Empty dict when the phone does not expose it.
    """
    ra = _find(raw, "WeightedRa")
    mohm = ra[0] if isinstance(ra, list) and ra else ra
    if not isinstance(mohm, (int, float)) or mohm <= 0:
        return {}
    return {"mohm": mohm, "high_above_mohm": RESISTANCE_HIGH_MOHM,
            "status": "high" if mohm > RESISTANCE_HIGH_MOHM else "ok", "provisional": True}


def analyse(raw: dict) -> dict:
    design = _find(raw, "DesignCapacity")
    current = _find(raw, "NominalChargeCapacity", "AppleRawMaxCapacity")
    pct_reported = _find(raw, "MaximumCapacityPercent")  # iPhone 15+ expose this directly

    if design and current:
        health, source = round(current / design * 100, 1), "computed"
    elif pct_reported:
        health, source = float(pct_reported), "reported by iOS"
    else:
        health, source = None, None

    temp = _find(raw, "Temperature", "VirtualTemperature")
    return {
        "health_pct": health,
        "health_source": source,
        "grade": grade(health),
        "design_capacity_mah": design,
        "current_max_capacity_mah": current,
        "cycle_count": _find(raw, "CycleCount"),
        "charge_pct": raw.get("CurrentCapacity"),
        "temperature_c": round(temp / 100, 1) if isinstance(temp, (int, float)) else None,
        "voltage_mv": _find(raw, "Voltage", "AppleRawBatteryVoltage"),
        "battery_serial": _find(raw, "Serial", "BatterySerialNumber"),
        "is_charging": _find(raw, "IsCharging"),
        "operating_hours": _find(raw, "TotalOperatingTime"),   # gas-gauge lifetime, hours installed
        "lifetime": lifetime(raw),
        "last_shutdown": last_shutdown(raw),
        "resistance": resistance(raw),
        "charging": charging(raw),
    }
