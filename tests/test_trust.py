from phonecert.system import trust

CLEAN = dict(find_my=False, cloud_config={"IsSupervised": False}, setup={}, profiles={"count": 0, "mdm_enrolled": False},
             jailbreak={"verdict": "none"}, device={"activation_state": "Activated", "unit_type": "New retail", "imei": "1"},
             parts={"flags": [], "build_dates": {"verdict": "consistent", "reasons": []}, "battery_age": {"reasons": []}})


def by_key(r):
    return {c["key"]: c for c in r["checks"]}


def test_erased_clean_phone_is_incomplete_until_blacklist_checked():
    r = trust.analyse(**CLEAN)
    assert r["verdict"] == "incomplete" and r["blockers"] == [] and r["unchecked"] == ["blacklist"]
    c = by_key(r)
    assert c["find_my"]["status"] == "pass" and c["supervision"]["status"] == "pass" and c["setup"]["status"] == "pass"


def test_find_my_on_blocks():
    r = trust.analyse(**{**CLEAN, "find_my": True})
    assert r["verdict"] == "blocked" and r["blockers"] == ["find_my"]
    assert "sign out" in by_key(r)["find_my"]["action"].lower()


def test_supervised_and_mdm_block():
    r = trust.analyse(**{**CLEAN, "cloud_config": {"IsSupervised": True},
                         "profiles": {"count": 1, "mdm_enrolled": True, "profiles": ["Acme MDM"]}})
    assert r["verdict"] == "blocked" and set(r["blockers"]) == {"supervision", "mdm"}


def test_owner_phone_like_iphone13():
    r = trust.analyse(find_my=True, cloud_config={"IsSupervised": False, "ConfigurationSource": 0},
                      setup={"SetupState": "SetupUsingiTunes", "RestoreState": "RestoredFromDevice"},
                      profiles={"count": 0, "mdm_enrolled": False}, jailbreak={"verdict": "suspicious"},
                      device={"activation_state": "Activated", "unit_type": "New retail", "imei": "359"},
                      parts={"flags": [], "build_dates": {"verdict": "consistent", "reasons": []}, "battery_age": {"reasons": []}})
    assert r["verdict"] == "blocked" and r["blockers"] == ["find_my"]
    assert set(r["warnings"]) == {"setup", "jailbreak"}


def test_unreadable_find_my_is_unknown_blocker():
    r = trust.analyse(**{**CLEAN, "find_my": {"error": "timeout"}})
    assert by_key(r)["find_my"]["status"] == "unknown" and "find_my" in r["unchecked"]


def test_parts_flags_become_warning():
    r = trust.analyse(**{**CLEAN, "parts": {"flags": [], "build_dates": {"verdict": "check", "reasons": ["Display built later"]}, "battery_age": {"reasons": []}}})
    assert by_key(r)["parts"]["status"] == "warn" and "parts" in r["warnings"]


def test_runnable_flags_when_lookup_available():
    r = trust.analyse(**CLEAN, imei_lookup={"available": True, "provider": "imei.info", "services": [27, 8], "cost_usd": 0.4})
    c = by_key(r)
    assert c["blacklist"]["runnable"] is True and c["blacklist"]["cost_usd"] == 0.4 and c["blacklist"]["action"] is None
    assert c["carrier_lock"]["runnable"] is True
    r2 = trust.analyse(**CLEAN)
    assert by_key(r2)["blacklist"]["runnable"] is False and "no IMEI provider" in by_key(r2)["blacklist"]["detail"]


def test_lookup_reason_is_shown():
    r = trust.analyse(**CLEAN, imei_lookup={"available": False, "reason": "no service ids: set PHONECERT_IMEIINFO_SERVICES=27,8 in .env"})
    assert "no service ids" in by_key(r)["blacklist"]["detail"]
