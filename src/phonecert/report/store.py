"""Saved reports: one JSON file per scan in reports/. Everything that reads or writes those files is here."""
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from phonecert.checks import catalog

REPORTS = Path(__file__).resolve().parents[3] / "reports"
TRASH = Path.home() / ".Trash"          # deleted scans go to the macOS Trash: recoverable until it is emptied
KEEP = {"imei_cache.json"}              # paid lookups; never listed as a scan, never removed by delete / clear


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def save(path: Path, report: dict) -> None:
    """Write a report. `saved_to` is where the file is, not part of what was scanned, so it is not stored."""
    Path(path).write_text(json.dumps({k: v for k, v in report.items() if k != "saved_to"}, indent=2, default=str))


def save_scan(report: dict) -> Path:
    """Store a fresh scan as <serial>_<date>_<time>.json and return its path."""
    REPORTS.mkdir(exist_ok=True)
    # The serial comes from the phone: keep only what a serial can contain, so it can never name a path.
    serial = re.sub(r"[^A-Za-z0-9-]", "", str(report["device"].get("serial") or ""))[:40] or "unknown"
    path = REPORTS / f"{serial}_{datetime.now():%Y%m%d_%H%M%S}.json"
    save(path, report)
    return path


def new_tests_only_report(label: str | None = None) -> Path:
    """A report with no scan data, for running the Safari tests without the cable.

    Same shape as a scan so the app and `phonecert reports` handle it; `source` marks it.
    """
    now = datetime.now()
    label = (label or "").strip() or "Phone without cable"
    safe = "".join(c if c.isalnum() else "-" for c in label).strip("-")[:30] or "phone"
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"nocable-{safe}_{now:%Y%m%d_%H%M%S}.json"
    report = {
        "scanned_at": now.isoformat(timespec="seconds"),
        "source": "tests-only",
        "device": {"name": label, "model": None, "serial": None, "imei": None},
        "battery": {}, "storage": {}, "sim": {},
        "system": {"panic_logs": {}, "jailbreak": {}, "profiles": {}},
        "parts": {},
        "tests": {"web": {}, "manual": {}, "auto": {}},
    }
    save(path, report)
    return path


def record_test(report_path: Path, kind: str, name: str, status: str, details=None, note: str | None = None) -> dict:
    """Store one result in the report file: tests[kind][name] = {...}. Returns the tests section."""
    r = load(report_path)
    tests = r.setdefault("tests", {"web": {}, "manual": {}})
    tests.setdefault(kind, {})[name] = {"status": status, "details": details, "note": note,
                                        "at": datetime.now().isoformat(timespec="seconds")}
    tests["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save(report_path, r)
    return tests


def list_reports() -> list[dict]:
    """Saved scans, newest first, with the fields a history list needs."""
    out = []
    for path in sorted(REPORTS.glob("*.json"), reverse=True):
        if path.name in KEEP:
            continue
        try:
            r = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        d, b = r.get("device", {}), r.get("battery", {})
        out.append({"path": str(path), "scanned_at": r.get("scanned_at"), "serial": d.get("serial"),
                    "model": d.get("model"), "name": d.get("name"), "ios_version": d.get("ios_version"),
                    "battery_health_pct": b.get("health_pct"), "battery_grade": b.get("grade"),
                    "source": r.get("source", "scan"),
                    "tests_done": catalog.summary(r.get("tests")).get("done", 0)})
    return out


def delete_reports(paths: list[str] | None) -> int:
    """Move saved scans to the Trash. `paths=None` means every scan. Returns how many were moved.

    Only *.json files directly inside reports/ are touched; anything else raises ValueError
    (the desktop app passes paths that came from the UI).
    """
    root = REPORTS.resolve()
    if paths is None:
        files = [f for f in root.glob("*.json") if f.name not in KEEP]
    else:
        files = [Path(x).resolve() for x in paths]
        for f in files:
            if f.parent != root or f.suffix != ".json" or f.name in KEEP:
                raise ValueError(f"not a saved scan: {f}")
    TRASH.mkdir(exist_ok=True)
    moved = 0
    for f in files:
        if not f.exists():
            continue
        dest, n = TRASH / f.name, 1
        while dest.exists():                       # same name already in the Trash
            dest, n = TRASH / f"{f.stem} {n}{f.suffix}", n + 1
        shutil.move(str(f), str(dest))
        moved += 1
    return moved
