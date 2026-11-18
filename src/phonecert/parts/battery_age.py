"""Is the battery as old as the phone?

A battery's gas gauge counts the hours it has been installed and powered
(BatteryData/LifetimeData/TotalOperatingTime, in hours). The logic board's
build date can be decoded from an old-format MLB serial. If the battery has
operated for roughly as many hours as the board has existed, it is the
original one; a much younger battery means a replacement (or a phone that sat
unused) and the buyer should ask.

Serial formats (older style, still used on the iPhone 13 / 2022):
  MLB      F3X 2 08 0000000000   factory, year digit, ISO week, unique…
  battery  FG9 2 033 0000000000  factory, year digit, day of year, unique…
Newer devices (iPhone 16 Pro) use randomised serials → dates unknown.
"""
import re
from datetime import date, datetime, timedelta

# Below this share of the phone's lifetime, the battery is suspiciously young.
NORMAL_RATIO = 0.80
# A battery dated this many days after the board was built is not the one fitted at the factory.
MAX_BATTERY_LAG_DAYS = 120

_MLB = re.compile(r"^[A-Z0-9]{3}(\d)(\d{2})")
_BATTERY = re.compile(r"^[A-Z0-9]{3}(\d)(\d{3})")


def _year(digit: int, release_year: int) -> int:
    """Resolve a single year digit: the first year >= release_year - 1 ending in that digit."""
    y = release_year - 1
    while y % 10 != digit:
        y += 1
    return y


def mlb_build_date(mlb_serial, release_year) -> date | None:
    m = _MLB.match(mlb_serial or "")
    if not m or not release_year:
        return None
    year, week = _year(int(m[1]), release_year), int(m[2])
    if not 1 <= week <= 53:
        return None
    return date.fromisocalendar(year, week, 1)


def battery_build_date(serial, release_year) -> date | None:
    m = _BATTERY.match(serial or "")
    if not m or not release_year:
        return None
    year, day = _year(int(m[1]), release_year), int(m[2])
    if not 1 <= day <= 366:
        return None
    return date(year, 1, 1) + timedelta(days=day - 1)


def assess(operating_hours, board_date: date | None, battery_date: date | None,
           today: date | None = None) -> dict:
    """Verdict: normal (battery lived with the phone), clarify (younger than the phone), unknown."""
    today = today or date.today()
    reasons = []
    expected = ratio = None
    if board_date:
        expected = round((today - board_date).total_seconds() / 3600)
        if operating_hours is not None and expected > 0:
            ratio = round(operating_hours / expected, 2)
            if ratio < NORMAL_RATIO:
                reasons.append(f"battery operated {operating_hours} h but the phone is {expected} h old "
                               f"({ratio:.0%}) — replaced battery or long storage")
        if battery_date and (battery_date - board_date).days > MAX_BATTERY_LAG_DAYS:
            reasons.append(f"battery built {battery_date} but board built {board_date} — not the factory battery")
    if reasons:
        verdict = "clarify"
    elif ratio is not None or (board_date and battery_date):
        verdict = "normal"
    else:
        verdict = "unknown"
    return {
        "verdict": verdict,
        "operating_hours": operating_hours,
        "board_built": board_date.isoformat() if board_date else None,
        "battery_built": battery_date.isoformat() if battery_date else None,
        "phone_age_hours": expected,
        "ratio": ratio,
        "reasons": reasons,
    }
