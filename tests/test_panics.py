from datetime import date

from phonecert.system import panics

TODAY = date(2026, 11, 10)


def test_no_panics():
    r = panics.analyse(["com.apple.app_1.ips", "JetsamEvent-2026-10-01-1.ips", "Retired"], today=TODAY)
    assert r["panic_count"] == 0 and r["risk"] == "none" and r["crash_file_count"] == 3


def test_companion_files_count_as_one_event():
    files = ["panic-full-2026-10-03-183012.0001.ips",
             "panic-base-2026-10-03-183012.0001.ips",
             "panic-slog-2026-10-03-183012.0001.ips"]
    r = panics.analyse(files, today=TODAY)
    assert r["panic_count"] == 1
    assert r["last_panic"] == "2026-10-03"
    assert r["days_since_last_panic"] == 38
    assert r["risk"] == "low"


def test_recent_or_repeated_panics_are_high_risk():
    assert panics.risk(1, 5) == "high"
    assert panics.risk(3, 400) == "high"
    assert panics.risk(2, 200) == "low"
    assert panics.risk(0, None) == "none"


def test_old_panic_format_and_subfolders():
    files = ["/panics/panic-full-2024-01-01-010101.0000.panic", "panic-full-2025-06-06-060606.0001.ips"]
    r = panics.analyse(files, today=TODAY)
    assert r["panic_count"] == 2 and r["last_panic"] == "2025-06-06"


def test_other_log_counts_and_ota_history():
    files = ["/LowBatteryLog-2026-10-01-1.ips", "/LowBatteryLog-2026-10-02-1.ips", "/JetsamEvent-2026-10-03-1.ips",
             "/ResetCounter-2026-11-09-131427.ips", "/OTAUpdate-2026-10-15-21-32-08.ips", "/OTAUpdate-2026-11-10-19-27-25.ips"]
    r = panics.analyse(files, today=TODAY)
    assert r["low_battery_logs"] == 2 and r["jetsam_events"] == 1 and r["watchdog_resets"] == 1
    assert r["ota_updates"] == {"count": 2, "first": "2026-10-15", "last": "2026-11-10"}
