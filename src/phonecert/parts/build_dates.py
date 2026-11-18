"""Were all the parts built before the logic board they sit on?

Apple component serials in the older factory format start with
  FFF Y WW …   factory code, last digit of the year, ISO week
(the battery uses FFF Y DDD, handled in battery_age). Parts are produced
before the board that receives them, so a part dated AFTER the board was
fitted later — a replacement — without needing Apple's pairing data.

Verified on the iPhone 13 (board built 2022-02-21): display, four cameras
and the Taptic Engine all decode to Nov 2021 – Feb 2022.
Undatable: Face ID projector, NAND (hex serial), randomised serials (2024+).
"""
import re
from datetime import date

from phonecert.parts.battery_age import _year

# A part dated this long after the board was built is not the one fitted at the factory.
MAX_LAG_DAYS = 120

_YWW = re.compile(r"^[A-Z0-9]{3}(\d)(\d{2})[A-Z0-9]{5,}$")

# Which inventory entries carry a datable serial, and how to find it.
COMPONENTS = {
    "display": lambda inv: inv["display"].get("panel_serial"),
    "camera back": lambda inv: inv["cameras"].get("back", {}).get("serial"),
    "camera ultrawide": lambda inv: inv["cameras"].get("back_ultrawide", {}).get("serial"),
    "camera tele": lambda inv: inv["cameras"].get("back_tele", {}).get("serial"),
    "camera front": lambda inv: inv["cameras"].get("front", {}).get("serial"),
    "camera front IR": lambda inv: inv["cameras"].get("front_ir", {}).get("serial"),
    "taptic engine": lambda inv: (inv["taptic"].get("serial") or "").split("+", 1)[0] or None,
}


def serial_date(serial, release_year) -> date | None:
    """FFF Y WW… → Monday of that ISO week, or None when the serial is not in that format."""
    m = _YWW.match(serial or "")
    if not m or not release_year:
        return None
    year, week = _year(int(m[1]), release_year), int(m[2])
    if not 1 <= week <= 53:
        return None
    try:
        return date.fromisocalendar(year, week, 1)
    except ValueError:
        return None


def assess(inventory: dict, board_date: date | None, release_year) -> dict:
    """Compare each component's build date with the board's. Verdict: consistent / check / unknown."""
    components = []
    reasons = []
    for part, pick in COMPONENTS.items():
        try:
            serial = pick(inventory)
        except (KeyError, AttributeError, TypeError):
            serial = None
        if not serial:
            continue
        built = serial_date(serial, release_year)
        entry = {"part": part, "serial": serial, "built": built.isoformat() if built else None,
                 "days_after_board": None, "verdict": "undated"}
        if built and board_date:
            lag = (built - board_date).days
            entry["days_after_board"] = lag
            if lag > MAX_LAG_DAYS:
                entry["verdict"] = "newer"
                reasons.append(f"{part.capitalize()} built {built} — {lag} days after the board ({board_date}) → replaced")
            else:
                entry["verdict"] = "original"
        components.append(entry)

    dated = [c for c in components if c["verdict"] != "undated"]
    if reasons:
        verdict = "check"
    elif dated:
        verdict = "consistent"
    else:
        verdict = "unknown"
    return {
        "verdict": verdict,
        "board_built": board_date.isoformat() if board_date else None,
        "components": components,
        "dated_count": len(dated),
        "reasons": reasons,
    }
