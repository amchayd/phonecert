"""Kernel panic logs — crashes of the OS itself, not of an app.

Repeated panics on a used phone usually point at hardware (baseband, NAND,
a damaged board after a drop or liquid). App crashes (*.ips of a process)
are normal and ignored here.

File names in CrashReporter look like:
  panic-full-2026-10-03-183012.0001.ips     the actual panic
  panic-base-2026-10-03-183012.0001.ips     companion files for the same event
  panic-slog-2026-10-03-183012.0001.ips
"""
import re
from datetime import date

_PANIC = re.compile(r"^panic-(?P<kind>full|base|slog|[a-z]+)-(?P<date>\d{4}-\d{2}-\d{2})-(?P<time>\d{6})")
_OTA = re.compile(r"^OTAUpdate-(\d{4}-\d{2}-\d{2})")


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _count(files, prefix: str) -> int:
    return sum(1 for f in files if _basename(f).startswith(prefix))


def ota_updates(files) -> dict:
    """OTAUpdate-<date>-…ips logs: one per update attempt. Last one ≈ last iOS update."""
    dates = sorted(m[1] for f in files if (m := _OTA.match(_basename(f))))
    return {"count": len(dates), "first": dates[0] if dates else None, "last": dates[-1] if dates else None}


def _events(files):
    """One entry per panic event, keyed by timestamp so companion files don't double count."""
    events = {}
    for name in files:
        base = name.rsplit("/", 1)[-1]
        m = _PANIC.match(base)
        if not m:
            continue
        key = f"{m['date']}-{m['time']}"
        events.setdefault(key, {"date": m["date"], "files": []})["files"].append(base)
    return [events[k] for k in sorted(events)]


def risk(count: int, last_days: int | None) -> str:
    """Translate panic history into a buyer-facing verdict.

    none  – no panic ever recorded
    low   – isolated/old panics (a single iOS bug can do that)
    high  – several panics, or a recent one → suspect hardware, test harder
    """
    if count == 0:
        return "none"
    if count >= 3 or (last_days is not None and last_days <= 30):
        return "high"
    return "low"


def analyse(files: list, today: date | None = None) -> dict:
    today = today or date.today()
    events = _events(files)
    last = date.fromisoformat(events[-1]["date"]) if events else None
    last_days = (today - last).days if last else None
    return {
        "panic_count": len(events),
        "last_panic": last.isoformat() if last else None,
        "days_since_last_panic": last_days,
        "risk": risk(len(events), last_days),
        "crash_file_count": len(files),
        "panic_files": [f for e in events for f in e["files"]],
        # Other hardware-relevant logs. Normal phones have a few; dozens is a smell.
        "low_battery_logs": _count(files, "LowBatteryLog"),
        "jetsam_events": _count(files, "JetsamEvent"),     # memory pressure kills
        "watchdog_resets": _count(files, "ResetCounter"),
        "ota_updates": ota_updates(files),
    }
