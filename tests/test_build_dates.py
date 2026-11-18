from datetime import date

from phonecert.parts import build_dates as bd

BOARD = date(2022, 2, 21)   # iPhone 13 MLB F3X208…
INV = {
    "display": {"panel_serial": "G9Q14500000000000"},
    "cameras": {"back": {"serial": "DNL14800000000000"}, "back_ultrawide": {"serial": "DNM20400000000000"},
                "front": {"serial": "DNM20200000000000"}, "front_ir": {"serial": "F8P20400000000000"}},
    "taptic": {"serial": "FTN20300000000000+XPB1XX"},
}


def test_serial_date_formats():
    assert bd.serial_date("G9Q14500000000000", 2021) == date(2021, 11, 8)
    assert bd.serial_date("DNM20200000000000", 2021) == date(2022, 1, 10)
    assert bd.serial_date("A2C1A300000000000", 2021) is None      # projector: other format
    assert bd.serial_date("0123456789abcdef", 2021) is None       # NAND hex
    assert bd.serial_date("F3YHXX000000000000", 2024) is None     # randomised
    assert bd.serial_date(None, 2021) is None


def test_factory_original_phone_is_consistent():
    r = bd.assess(INV, BOARD, 2021)
    assert r["verdict"] == "consistent" and r["reasons"] == []
    assert r["dated_count"] == 6
    assert {c["part"]: c["verdict"] for c in r["components"]} == {
        "display": "original", "camera back": "original", "camera ultrawide": "original",
        "camera front": "original", "camera front IR": "original", "taptic engine": "original"}
    assert all(c["days_after_board"] <= 0 for c in r["components"])


def test_display_built_two_years_later_is_flagged():
    inv = {**INV, "display": {"panel_serial": "G9Q42200000000000"}}   # 2024 week 22
    r = bd.assess(inv, BOARD, 2021)
    assert r["verdict"] == "check"
    assert r["reasons"] == ["Display built 2024-05-27 — 826 days after the board (2022-02-21) → replaced"]
    assert next(c for c in r["components"] if c["part"] == "display")["verdict"] == "newer"


def test_within_grace_period_is_original():
    inv = {**INV, "taptic": {"serial": "FTN21200000000000"}}         # 2022 week 12, 3 weeks after board
    assert bd.assess(inv, BOARD, 2021)["verdict"] == "consistent"


def test_no_board_date_is_unknown():
    r = bd.assess(INV, None, 2021)
    assert r["verdict"] == "unknown" and all(c["verdict"] == "undated" for c in r["components"])


def test_missing_sections_do_not_crash():
    assert bd.assess({"display": {}, "cameras": {}, "taptic": {}}, BOARD, 2021)["verdict"] == "unknown"
