"""Battery under load: sample the gauge over USB while the phone rests, then works, and judge the result.

The phone's test page generates the load; the Mac measures. `verdict()` is pure (lists of samples in,
dict out); `LoadSampler` does the polling; `read_gauge()` is the only part that touches the device.
"""
import threading
from datetime import datetime

from phonecert.battery.health import RESISTANCE_HIGH_MOHM
from phonecert.device.reader import battery_info

# Battery under load. The verdict is the battery's internal resistance (slope of voltage against
# current), which does not depend on how hard the phone worked or on whether it was charging.
# 150 mΩ is provisional: the test iPhone 13 (75 % health, iOS says "Service") reports 153 mΩ itself.
RESISTANCE_FAIL_MOHM = RESISTANCE_HIGH_MOHM   # one limit for the scan figure and for this test
MIN_CURRENT_SPREAD_MA = 300   # below this the slope is noise → inconclusive
SAMPLE_EVERY_S = 3.0          # the iPhone 13 gauge only refreshes about every 20 s
MIN_READINGS = 4               # distinct gauge refreshes needed for a verdict
TEMP_RISE_FAIL_C = 8.0
NEARLY_FULL_PCT = 70                # above this the charger tapers and the load hardly changes the battery current


def read_gauge() -> dict | None:
    """One gauge reading over USB (voltage mV, current mA, temperature °C) — None when no phone."""
    try:
        b = battery_info()
    except Exception:  # noqa: BLE001 — sampling must never break the test server
        return None
    temp = b.get("Temperature")
    ra = (b.get("BatteryData") or {}).get("WeightedRa")
    return {"at": datetime.now().isoformat(timespec="seconds"), "voltage_mv": b.get("Voltage"),
            "current_ma": b.get("InstantAmperage", b.get("Amperage")),
            "temperature_c": round(temp / 100, 1) if isinstance(temp, (int, float)) else None,
            "charge_pct": b.get("CurrentCapacity"), "charging": b.get("IsCharging"),
            "gauge_update": b.get("UpdateTime"),
            "gauge_ra_mohm": ra[0] if isinstance(ra, list) and ra else ra}


def _distinct(samples: list[dict]) -> list[dict]:
    """Usable readings, without repeats of the same gauge refresh (the gauge updates slower than we poll)."""
    out, seen = [], set()
    for x in samples:
        if not x or x.get("voltage_mv") is None or x.get("current_ma") is None:
            continue
        key = (x.get("gauge_update"), x["voltage_mv"], x["current_ma"])
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


def resistance_mohm(samples: list[dict]) -> tuple[float | None, int]:
    """Internal resistance = least-squares slope of voltage (mV) on current (mA), in mΩ.

    V = OCV + I·R holds while charging (I > 0) and discharging (I < 0), so the charger does not
    hide a weak battery. Returns (resistance or None, current spread in mA).
    """
    pts = [(x["current_ma"], x["voltage_mv"]) for x in _distinct(samples)]
    if len(pts) < MIN_READINGS:
        return None, 0
    cur = [i for i, _ in pts]
    spread = max(cur) - min(cur)
    if spread < MIN_CURRENT_SPREAD_MA:
        return None, spread
    mi, mv = sum(cur) / len(pts), sum(v for _, v in pts) / len(pts)
    slope = sum((i - mi) * (v - mv) for i, v in pts) / sum((i - mi) ** 2 for i in cur)
    return (round(slope * 1000, 1) if slope > 0 else None), spread


def verdict(samples: list[dict]) -> dict:
    """pass / fail from the internal resistance; skip when there is nothing trustworthy to judge."""
    good = _distinct(samples)
    if len(good) < MIN_READINGS:
        why = ("no battery readings: connect the phone to the Mac with the cable" if not good
               else f"too few battery readings: the gauge refreshed only {len(good)} times, {MIN_READINGS} needed")
        return {"status": "skip", "samples": len(samples), "readings": len(good), "reason": why}
    volts = [x["voltage_mv"] for x in good]
    temps = [x["temperature_c"] for x in good if x.get("temperature_c") is not None]
    r, spread = resistance_mohm(samples)
    out = {"samples": len(samples), "readings": len(good), "resistance_mohm": r, "current_spread_ma": spread,
           "gauge_ra_mohm": next((x["gauge_ra_mohm"] for x in good if x.get("gauge_ra_mohm") is not None), None),
           "start_mv": volts[0], "min_mv": min(volts), "sag_mv": volts[0] - min(volts),
           "temp_start_c": temps[0] if temps else None,
           "temp_rise_c": round(max(temps) - temps[0], 1) if len(temps) >= 2 else None,
           "charging": any(x.get("charging") for x in good), "fail_above_mohm": RESISTANCE_FAIL_MOHM}
    if r is None:
        nearly_full = out["charging"] and max(x.get("charge_pct") or 0 for x in good) >= NEARLY_FULL_PCT
        advice = (" The battery is nearly full, so it takes little charging current and the load barely moves it:"
                  f" run the test below {NEARLY_FULL_PCT} % charge." if nearly_full else "")
        return {"status": "skip", **out,
                "reason": f"inconclusive: battery current changed by only {spread} mA, or the readings were too noisy.{advice}"}
    hot = out["temp_rise_c"] is not None and out["temp_rise_c"] > TEMP_RISE_FAIL_C
    # Judge on the worse of the two figures: ours (short, ~1 A step) and the gauge's own long-term one.
    # On the iPhone 13 they disagree (58 vs 153 mΩ), so a low measurement alone must not pass the battery.
    worst = max(r, out["gauge_ra_mohm"] or 0)
    return {"status": "fail" if worst > RESISTANCE_FAIL_MOHM or hot else "pass", **out, "judged_on_mohm": worst}


def too_full_to_measure(sample: dict | None) -> bool:
    """On the charger and nearly full: the run would come out inconclusive, so say so before it starts."""
    return bool(sample and sample.get("charging") and (sample.get("charge_pct") or 0) >= NEARLY_FULL_PCT)


class LoadSampler:
    """Polls the battery gauge while the phone rests, then works; each sample is tagged with its phase."""

    def __init__(self):
        self.samples: list[dict] = []
        self.phase = "rest"
        self._stop = threading.Event()
        self._thread = None

    def start(self, seconds: int = 180) -> bool:
        """Begin sampling. Returns False when the gauge cannot be read (no cable)."""
        self.stop()
        self.phase, self._stop = "rest", threading.Event()
        first = read_gauge()
        self.samples = [first and {**first, "phase": "rest"}]
        if first is None:
            return False
        def run():
            deadline = datetime.now().timestamp() + seconds   # safety net if the page never says stop
            while not self._stop.wait(SAMPLE_EVERY_S) and datetime.now().timestamp() < deadline:
                x = read_gauge()
                self.samples.append(x and {**x, "phase": self.phase})
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        if self._thread:
            self._stop.set()
            self._thread.join(timeout=8)
            self._thread = None
