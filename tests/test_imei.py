import json
from datetime import datetime, timedelta

import pytest

from phonecert.checks import imei
from phonecert.system import trust

IMEI = "359451180000012"


def test_normalise_structured_clean():
    r = imei.normalise({"result": {"Blacklist Status": "Clean", "Sim-Lock Status": "Unlocked", "Find My iPhone": "OFF",
                                   "Carrier": "Unlocked"}})
    assert r["blacklist"]["status"] == "pass" and r["carrier_lock"]["status"] == "pass" and r["find_my"]["status"] == "pass"


def test_normalise_blacklisted_locked_html():
    html = "Model: iPhone 13<br>Blacklist Status: BLACKLISTED (Lost/Stolen)<br>Sim-Lock Status: Locked<br>Carrier: Orange France<br>Find My iPhone: ON"
    r = imei.normalise({"result": html})
    assert r["blacklist"]["status"] == "fail" and "Lost" in r["blacklist"]["detail"]
    assert r["carrier_lock"]["status"] == "fail" and r["carrier_lock"]["carrier"] == "Orange France"
    assert r["find_my"]["status"] == "fail"


def test_normalise_unknown_fields():
    r = imei.normalise({"result": {"Something": "else"}})
    assert {r["blacklist"]["status"], r["carrier_lock"]["status"], r["find_my"]["status"]} == {"unknown"}


def test_check_imei_mock_and_cache(tmp_path):
    cache = tmp_path / "cache.json"
    first = imei.check_imei(IMEI, imei.MockProvider(), cache_file=cache)
    assert first["cached"] is False and first["blacklist"]["status"] == "pass" and first["provider"] == "mock"
    second = imei.check_imei(IMEI, imei.MockProvider(), cache_file=cache)
    assert second["cached"] is True
    forced = imei.check_imei(IMEI, imei.MockProvider(), cache_file=cache, force=True)
    assert forced["cached"] is False
    assert list(json.loads(cache.read_text()).keys()) == [f"mock:{imei.SERVICE_FULL}:{IMEI}"]


def test_cache_expires(tmp_path):
    cache = tmp_path / "cache.json"
    imei.check_imei(IMEI, imei.MockProvider(), cache_file=cache)
    data = json.loads(cache.read_text())
    for v in data.values():
        v["checked_at"] = (datetime.now() - timedelta(days=8)).isoformat(timespec="seconds")
    cache.write_text(json.dumps(data))
    assert imei.check_imei(IMEI, imei.MockProvider(), cache_file=cache)["cached"] is False


def test_rejects_non_imei():
    with pytest.raises(imei.ImeiError):
        imei.check_imei("12345", imei.MockProvider(), cache_file=None)


def test_provider_from_env(monkeypatch):
    monkeypatch.delenv("PHONECERT_SICKW_KEY", raising=False)
    monkeypatch.setattr(imei, "ENV_FILE", imei.ROOT / "definitely-missing.env")
    assert imei.provider_from_env() is None
    assert isinstance(imei.provider_from_env(mock=True), imei.MockProvider)
    monkeypatch.setenv("PHONECERT_SICKW_KEY", "abc")
    assert isinstance(imei.provider_from_env(), imei.SickwProvider)


def test_sickw_error_payload_raises(monkeypatch):
    class FakeResp:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(imei.urllib.request, "urlopen",
                        lambda req, timeout: FakeResp(b'{"result": "Error A01: API KEY is Wrong!", "status": "error", "imei": "1"}'))
    with pytest.raises(imei.ImeiError, match="A01"):
        imei.SickwProvider("bad").lookup(IMEI, 61)


BASE = dict(find_my=False, cloud_config={"IsSupervised": False}, setup={}, profiles={"count": 0, "mdm_enrolled": False},
            jailbreak={"verdict": "none"}, device={"activation_state": "Activated", "unit_type": "New retail", "imei": IMEI})


def test_trust_uses_imei_result():
    ic = imei.check_imei(IMEI, imei.MockProvider(), cache_file=None)
    r = trust.analyse(**BASE, imei_check=ic)
    c = {x["key"]: x for x in r["checks"]}
    assert c["blacklist"]["status"] == "pass" and c["carrier_lock"]["status"] == "pass"
    assert r["verdict"] == "clear"


def test_trust_blacklisted_blocks():
    ic = imei.check_imei(IMEI, imei.MockProvider({"Blacklist Status": "Blacklisted"}), cache_file=None)
    r = trust.analyse(**BASE, imei_check=ic)
    assert r["verdict"] == "blocked" and r["blockers"] == ["blacklist"]


def test_trust_lookup_error_stays_pending():
    r = trust.analyse(**BASE, imei_check={"error": "sickw request failed"})
    c = {x["key"]: x for x in r["checks"]}
    assert c["blacklist"]["status"] == "not_checked" and "lookup failed" in c["blacklist"]["detail"]


def test_lock_wording_edge_cases():
    n = lambda lock: imei.normalise({"result": {"Sim-Lock Status": lock}})["carrier_lock"]["status"]
    assert n("Unlocked") == "pass" and n("Locked") == "fail" and n("No SIM restrictions") == "pass" and n("Lock: ON") == "fail"
    b = lambda v: imei.normalise({"result": {"Blacklist Status": v}})["blacklist"]["status"]
    assert b("Clean") == "pass" and b("Not blacklisted") == "pass" and b("BLACKLISTED") == "fail" and b("Reported lost") == "fail"
    f = lambda v: imei.normalise({"result": {"Find My iPhone": v}})["find_my"]["status"]
    assert f("OFF") == "pass" and f("ON") == "fail" and f("Lost mode") == "fail"


def test_verdicts_fail_closed_on_mixed_answers():
    b = lambda v: imei.normalise({"result": {"Blacklist Status": v}})["blacklist"]["status"]
    assert b("Blacklisted, not paid") == "fail" and b("Not clean") == "fail" and b("No longer clean: lost") == "fail"
    assert b("Clean (not blacklisted)") == "pass" and b("Never reported lost or stolen") == "pass"
    assert b("Pending review") == "unknown"
    n = lambda lock: imei.normalise({"result": {"Sim-Lock Status": lock}})["carrier_lock"]["status"]
    assert n("Unlocked, previously locked to a carrier") == "fail" and n("Not locked") == "unknown"
    f = lambda v: imei.normalise({"result": {"Find My iPhone": v}})["find_my"]["status"]
    assert f("OFF (lost mode: on)") == "fail"


def test_imeiinfo_services_never_fetches_the_next_link_itself(monkeypatch):
    urls = []
    def fake(req, timeout):
        urls.append(req.full_url)
        nxt = '"http://169.254.169.254/latest/?page=2"'
        return _Resp(('{"next": %s, "results": [{"id": 1, "name": "A"}]}' % nxt).encode())
    monkeypatch.setattr(imei.urllib.request, "urlopen", fake)
    items = imei.ImeiInfoProvider("k").services()
    assert all(u.startswith(imei.IMEIINFO_URL + "/api/service/services/") for u in urls)
    assert len(urls) == 2 and len(items) == 2          # same page parameter twice → stops instead of looping


class _Resp:
    def __init__(self, body): self.body = body
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *a): pass


def test_imeiinfo_lookup_done(monkeypatch):
    seen = {}
    def fake(req, timeout):
        seen["url"] = req.full_url
        return _Resp(b'{"id": 7, "status": "Done", "token_request_price": "0.02", "result": {"Blacklist Status": "Clean", "SIM-Lock": "Unlocked"}}')
    monkeypatch.setattr(imei.urllib.request, "urlopen", fake)
    r = imei.ImeiInfoProvider("k").lookup(IMEI, 12)
    assert "/api-sync/check/12/" in seen["url"] and "API_KEY=k" in seen["url"] and f"imei={IMEI}" in seen["url"]
    assert r["status"] == "success" and r["price"] == "0.02" and r["result"]["SIM-Lock"] == "Unlocked"


def test_imeiinfo_bad_token_and_rejected(monkeypatch):
    monkeypatch.setattr(imei.urllib.request, "urlopen", lambda req, timeout: _Resp(b'{"detail": "Token is invalid."}'))
    with pytest.raises(imei.ImeiError, match="Token is invalid"):
        imei.ImeiInfoProvider("bad").lookup(IMEI, 1)
    monkeypatch.setattr(imei.urllib.request, "urlopen", lambda req, timeout: _Resp(b'{"status": "Rejected", "result": null}'))
    with pytest.raises(imei.ImeiError, match="Rejected"):
        imei.ImeiInfoProvider("k").lookup(IMEI, 1)


def test_imeiinfo_services_pagination(monkeypatch):
    pages = {
        "/api/service/services/": b'{"count": 3, "next": "https://dash.imei.info/api/service/services/?page=2", "results": [{"id": 1, "name": "A", "price": "0.02"}, {"id": 2, "name": "B", "price": "0.10"}]}',
        "page=2": b'{"count": 3, "next": null, "results": [{"id": 3, "name": "C", "price": "0.50"}]}',
    }
    def fake(req, timeout):
        url = req.full_url
        return _Resp(pages["page=2"] if "page=2" in url else pages["/api/service/services/"])
    monkeypatch.setattr(imei.urllib.request, "urlopen", fake)
    items = imei.ImeiInfoProvider("k").services()
    assert [i["id"] for i in items] == [1, 2, 3] and items[2]["price"] == "0.50"


def test_provider_precedence_and_default_service(monkeypatch):
    monkeypatch.setattr(imei, "ENV_FILE", imei.ROOT / "definitely-missing.env")
    monkeypatch.delenv("PHONECERT_SICKW_KEY", raising=False)
    monkeypatch.delenv("PHONECERT_IMEIINFO_SERVICE", raising=False)
    monkeypatch.setenv("PHONECERT_IMEIINFO_KEY", "x")
    p = imei.provider_from_env()
    assert isinstance(p, imei.ImeiInfoProvider) and imei.default_service(p) == 27
    monkeypatch.setenv("PHONECERT_IMEIINFO_SERVICE", "42")
    assert imei.default_service(p) == 42
    assert imei.default_service(imei.SickwProvider("y")) == imei.SERVICE_FULL


def test_imeiinfo_services_plain_list(monkeypatch):
    monkeypatch.setattr(imei.urllib.request, "urlopen",
                        lambda req, timeout: _Resp(b'[{"id": 9, "name": "X", "price": "0.05"}]'))
    assert imei.ImeiInfoProvider("k").services() == [{"id": 9, "name": "X", "price": "0.05", "brand": None, "slug": None}]


def test_multi_service_merge(tmp_path):
    class Two:
        name = "two"
        def lookup(self, imei, service):
            return {"status": "success", "imei": imei, "price": "0.20",
                    "result": {"Blacklist Status": "Clean"} if service == 27 else {"Sim-Lock Status": "Locked", "Carrier": "Orange"}}
    r = imei.check_imei_multi(IMEI, Two(), [27, 8], cache_file=tmp_path / "c.json")
    assert r["blacklist"]["status"] == "pass" and r["carrier_lock"]["status"] == "fail"
    assert r["carrier_lock"]["carrier"] == "Orange" and r["find_my"]["status"] == "unknown"
    assert r["service"] == "27,8" and r["raw_price"] == 0.4 and set(r["raw"]) == {"27", "8"}
    assert imei.check_imei_multi(IMEI, Two(), [27, 8], cache_file=tmp_path / "c.json")["cached"] is True


def test_default_services_parsing(monkeypatch):
    monkeypatch.setattr(imei, "ENV_FILE", imei.ROOT / "definitely-missing.env")
    monkeypatch.setenv("PHONECERT_IMEIINFO_SERVICES", "27, 8")
    assert imei.default_services(imei.ImeiInfoProvider("k")) == [27, 8]
    monkeypatch.delenv("PHONECERT_IMEIINFO_SERVICES")
    monkeypatch.delenv("PHONECERT_IMEIINFO_SERVICE", raising=False)
    assert imei.default_services(imei.ImeiInfoProvider("k")) == [27, 8] and imei.default_services(imei.MockProvider()) == [61]


def test_estimated_cost():
    assert imei.estimated_cost(imei.ImeiInfoProvider("k"), [27, 8]) == 0.4
    assert imei.estimated_cost(imei.ImeiInfoProvider("k"), [27, 999]) is None
    assert imei.estimated_cost(imei.SickwProvider("k"), [61]) == 0.1


def test_mock_switch_via_env(monkeypatch):
    monkeypatch.setattr(imei, "ENV_FILE", imei.ROOT / "definitely-missing.env")
    monkeypatch.setenv("PHONECERT_IMEI_MOCK", "1")
    assert isinstance(imei.provider_from_env(), imei.MockProvider)


# ---- settings (the app's Settings screen) ----

def _settings_env(monkeypatch, tmp_path, text=None):
    from phonecert import settings
    for f in settings.FIELDS:
        monkeypatch.delenv(f.env, raising=False)
    monkeypatch.delenv("PHONECERT_IMEI_MOCK", raising=False)
    monkeypatch.delenv("PHONECERT_IMEIINFO_SERVICE", raising=False)
    path = tmp_path / ".env"
    if text is not None:
        path.write_text(text)
    monkeypatch.setattr(imei, "ENV_FILE", path)
    return settings, path


def test_settings_save_keeps_other_lines_and_never_returns_the_key(monkeypatch, tmp_path):
    settings, path = _settings_env(monkeypatch, tmp_path, "# my notes\nOTHER=1\nPHONECERT_IMEIINFO_KEY=\n")
    settings.write({"imeiinfo_key": "  secret-key-abcd1234 ", "imeiinfo_services": "27, 8"})
    assert path.read_text() == "# my notes\nOTHER=1\nPHONECERT_IMEIINFO_KEY=secret-key-abcd1234\nPHONECERT_IMEIINFO_SERVICES=27, 8\n"
    assert path.stat().st_mode & 0o777 == 0o600
    view = settings.read()
    assert view["provider"] == "imei.info" and view["services"] == [27, 8]
    assert view["fields"]["imeiinfo_key"] == {"set": True, "from_environment": False, "hint": "…1234"}
    assert "secret-key" not in json.dumps(view)


def test_settings_empty_value_removes_and_bad_values_are_refused(monkeypatch, tmp_path):
    settings, path = _settings_env(monkeypatch, tmp_path, "PHONECERT_SICKW_KEY=abcdefgh\n")
    assert settings.read()["provider"] == "sickw"
    settings.write({"sickw_key": ""})
    assert settings.read()["provider"] is None and settings.read()["fields"]["sickw_key"]["set"] is False
    for bad in ({"nope": "x"}, {"imeiinfo_services": "27;rm"}, {"imeiinfo_key": "a\nINJECTED=1"}):
        with pytest.raises(ValueError):
            settings.write(bad)
    assert "INJECTED" not in path.read_text()


def test_settings_check(monkeypatch, tmp_path):
    settings, _ = _settings_env(monkeypatch, tmp_path)
    assert settings.check()["ok"] is False
    settings.write({"imeiinfo_key": "abcdefgh"})
    monkeypatch.setattr(imei.ImeiInfoProvider, "account", lambda self: {"username": "x", "balance": "4.60"})
    assert settings.check() == {"ok": True, "provider": "imei.info", "detail": "The key works. Balance: 4.60 USD.", "balance": "4.60"}
    monkeypatch.setattr(imei.ImeiInfoProvider, "account", lambda self: {"detail": "Token is invalid."})
    assert settings.check()["ok"] is False and "invalid" in settings.check()["detail"]
