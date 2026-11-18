from datetime import date

from phonecert.device.models import release_year
from phonecert.parts import battery_age as ba

TODAY = date(2026, 11, 10)


def test_mlb_date_iphone13():
    # F3X 2 08 … → 2022, ISO week 8
    assert ba.mlb_build_date("F3X2080000000000", 2021) == date(2022, 2, 21)


def test_battery_date_iphone13():
    # FG9 2 033 … → 2022, day 33
    assert ba.battery_build_date("FG920330000000000", 2021) == date(2022, 2, 2)


def test_year_digit_resolves_against_release_year():
    assert ba._year(2, 2021) == 2022
    assert ba._year(1, 2021) == 2021
    assert ba._year(0, 2021) == 2020   # units built the year before launch


def test_randomised_serials_give_no_date():
    assert ba.mlb_build_date("F3YHXX000000000000", 2024) is None
    assert ba.battery_build_date("F5DHXX000000000000", 2024) is None
    assert ba.mlb_build_date(None, 2024) is None


def test_original_battery_is_normal():
    r = ba.assess(40951, date(2022, 2, 21), date(2022, 2, 2), today=TODAY)
    assert r["verdict"] == "normal" and r["ratio"] >= 0.95 and r["reasons"] == []


def test_young_battery_needs_clarification():
    r = ba.assess(5000, date(2022, 2, 21), None, today=TODAY)
    assert r["verdict"] == "clarify" and "replaced battery" in r["reasons"][0]


def test_battery_newer_than_board_needs_clarification():
    r = ba.assess(None, date(2022, 2, 21), date(2024, 6, 1), today=TODAY)
    assert r["verdict"] == "clarify" and "not the factory battery" in r["reasons"][0]


def test_no_data_is_unknown():
    assert ba.assess(None, None, None, today=TODAY)["verdict"] == "unknown"
    assert ba.assess(40951, None, None, today=TODAY)["verdict"] == "unknown"


def test_release_years():
    assert release_year("iPhone14,5") == 2021 and release_year("iPhone17,1") == 2024
    assert release_year("nope") is None
