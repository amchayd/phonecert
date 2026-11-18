import time
import json
import threading
import urllib.request

from phonecert.checks import battery_load, catalog, lan, webtests
from phonecert.report import store


def make_report(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"device": {"model": "iPhone 13"}}))
    return p


def test_record_and_summary(tmp_path):
    p = make_report(tmp_path)
    store.record_test(p, "manual", "buttons", "pass", note="all good")
    tests = store.record_test(p, "web", "touch", "fail", details={"missed": 3})
    r = json.loads(p.read_text())
    assert r["tests"]["manual"]["buttons"]["note"] == "all good" and r["tests"]["web"]["touch"]["details"] == {"missed": 3}
    assert catalog.summary(tests) == {"done": 2, "total": len(catalog.WEB_TESTS) + len(catalog.MANUAL_TESTS) + len(catalog.AUTO_TESTS), "failed": ["touch"]}
    assert catalog.summary(None)["done"] == 0


def test_server_round_trip(tmp_path):
    p = make_report(tmp_path)
    server = webtests.make_server(p, port=0, host="127.0.0.1", token="secret1")
    t = threading.Thread(target=server.serve_forever, daemon=True); t.start()
    base = f"http://127.0.0.1:{server.server_port}"
    k = "?k=secret1"

    def expect(code, url, data=None):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
        try:
            urllib.request.urlopen(req); assert False, f"expected {code}"
        except urllib.error.HTTPError as e:
            assert e.code == code
    try:
        html = urllib.request.urlopen(base + "/" + k).read().decode()
        assert "<html" in html.lower() and "touch" in html.lower()
        state = json.loads(urllib.request.urlopen(base + "/api/state" + k).read())
        assert state["device"] == "iPhone 13" and "touch" in state["web_tests"]
        req = urllib.request.Request(base + "/api/result" + k, data=json.dumps({"name": "speaker", "status": "pass", "details": {"top": True}}).encode(),
                                     headers={"Content-Type": "application/json"})
        ok = json.loads(urllib.request.urlopen(req).read())
        assert ok["ok"] and ok["summary"]["done"] == 2   # speaker + the automatic wifi result
        assert json.loads(p.read_text())["tests"]["web"]["speaker"]["status"] == "pass"
        expect(400, base + "/api/result" + k, b'{"name": "nope", "status": "pass"}')
        expect(404, base + "/../pyproject.toml" + k)
        expect(404, base + "/index.html/../../pyproject.toml" + k)
        expect(403, base + "/api/state")                          # no token
        assert "6-digit code" in urllib.request.urlopen(base + "/").read().decode()   # bare address → join page
        expect(403, base + "/api/result?k=wrong", b'{"name": "speaker", "status": "fail"}')
        assert json.loads(p.read_text())["tests"]["web"]["speaker"]["status"] == "pass"   # unchanged
    finally:
        server.shutdown(); server.server_close()


def test_lan_ip_is_ipv4():
    ip = lan.lan_ip()
    assert ip.count(".") == 3


def test_auto_from_scan_and_touch_flags():
    from phonecert.parts import inventory
    report = {"battery": {"charging": {"status": "pass", "current_ma": 900, "adapter_watts": 15}},
              "parts": {"touch": {"critical_errors_total": 3, "resets": 1}}}
    a = catalog.auto_from_scan(report)
    assert a["charging"]["status"] == "pass" and "900 mA" in a["charging"]["details"]["summary"]
    assert a["touch_controller"]["status"] == "fail" and a["touch_controller"]["details"] == {"critical_errors": 3, "resets": 1}
    assert catalog.auto_from_scan({})["charging"] if False else catalog.auto_from_scan({}) == {}
    inv = inventory.analyse({"touch": {"Multitouch ID": 1, "Critical Errors Accumulator": 3, "ResetCount": 1}}, {})
    assert any("ghost touches" in f for f in inventory.flags(inv))


def _samples(r_mohm, currents, ocv=3900):
    return [{"voltage_mv": ocv + i * r_mohm / 1000, "current_ma": i, "temperature_c": 30.0, "gauge_update": n}
            for n, i in enumerate(currents)]


def test_load_verdict():
    # charging at rest (+2 A), battery current falls under load: slope gives the resistance either way
    v = battery_load.verdict(_samples(90, [2000, 1950, 900, 600, 500]))
    assert v["status"] == "pass" and v["resistance_mohm"] == 90.0 and v["current_spread_ma"] == 1500
    assert battery_load.verdict(_samples(240, [2000, 1200, 400, -300]))["status"] == "fail"
    assert battery_load.verdict(_samples(240, [-200, -600, -900, -1500]))["status"] == "fail"   # discharging works too


def test_load_verdict_skips_instead_of_failing():
    low = [{**x, "gauge_ra_mohm": 153} for x in _samples(58, [1868, 770, 1098, 900])]         # iPhone 13, 11 Nov 2026
    v = battery_load.verdict(low)
    assert v["status"] == "fail" and v["resistance_mohm"] == 58.0 and v["judged_on_mohm"] == 153  # gauge figure wins
    assert battery_load.verdict(_samples(58, [1868, 770, 1098]))["status"] == "skip"         # 3 refreshes: too few
    assert battery_load.verdict([None, None, None])["status"] == "skip"                    # no cable
    flat = battery_load.verdict(_samples(240, [2000, 1990, 1950, 1900]))
    assert flat["status"] == "skip" and "inconclusive" in flat["reason"]                    # load too small to tell
    same = [{"voltage_mv": 3900, "current_ma": 2000, "gauge_update": 7}] * 6                # gauge never refreshed
    assert battery_load.verdict(same)["status"] == "skip"


def test_state_records_wifi_and_blob_and_load(tmp_path, monkeypatch):
    p = make_report(tmp_path)
    ticks = iter(range(10 ** 6))
    def fake():
        n = next(ticks); i = 2000 - 400 * min(n, 4)
        return {"voltage_mv": 3900 + i * 0.09, "current_ma": i, "temperature_c": 30.0, "gauge_update": n}
    monkeypatch.setattr(battery_load, "read_gauge", fake)
    monkeypatch.setattr(battery_load, "SAMPLE_EVERY_S", 0.02)
    server = webtests.make_server(p, port=0, host="127.0.0.1", token="t")
    t = threading.Thread(target=server.serve_forever, daemon=True); t.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        json.loads(urllib.request.urlopen(base + "/api/state?k=t").read())
        assert json.loads(p.read_text())["tests"]["auto"]["wifi"]["status"] == "pass"
        blob = urllib.request.urlopen(base + "/api/blob?k=t&mb=1").read()
        assert len(blob) == 1024 * 1024
        req = urllib.request.Request(base + "/api/load?k=t&phase=start", data=b"", method="POST")
        assert json.loads(urllib.request.urlopen(req).read())["gauge"] is True
        urllib.request.urlopen(urllib.request.Request(base + "/api/load?k=t&phase=load", data=b"", method="POST"))
        time.sleep(0.3)
        req = urllib.request.Request(base + "/api/load?k=t&phase=stop", data=b"", method="POST")
        res = json.loads(urllib.request.urlopen(req).read())
        assert res["status"] == "pass" and json.loads(p.read_text())["tests"]["web"]["battery_load"]["status"] == "pass"
    finally:
        server.shutdown(); server.server_close()


def test_self_signed_cert(tmp_path, monkeypatch):
    monkeypatch.setattr(lan, "CERT_DIR", tmp_path / "certs")
    pair = lan.self_signed_cert("127.0.0.1")
    if pair is None:
        return   # no openssl on this machine
    assert pair[0].exists() and pair[1].exists()
    server = webtests.make_server(make_report(tmp_path), port=0, host="127.0.0.1", token="t", https=True, ip="127.0.0.1")
    assert server.scheme == "https"
    server.server_close()


def test_new_report(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "REPORTS", tmp_path)
    path = store.new_tests_only_report("iPhone 13 blue / seller Max")
    assert path.parent == tmp_path and path.name.startswith("nocable-iPhone-13-blue")
    r = json.loads(path.read_text())
    assert r["source"] == "tests-only" and r["device"]["name"] == "iPhone 13 blue / seller Max" and r["tests"]["auto"] == {}
    store.record_test(path, "manual", "buttons", "pass")
    assert catalog.summary(json.loads(path.read_text())["tests"])["done"] == 1
    assert store.new_tests_only_report("").name.startswith("nocable-Phone-without-cable")


def test_result_via_get_fallback(tmp_path):
    p = make_report(tmp_path)
    server = webtests.make_server(p, port=0, host="127.0.0.1", token="t")
    t = threading.Thread(target=server.serve_forever, daemon=True); t.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        ok = json.loads(urllib.request.urlopen(base + '/api/result?k=t&name=touch&status=fail&details=%7B%22missed%22%3A2%7D').read())
        assert ok["ok"] and json.loads(p.read_text())["tests"]["web"]["touch"] ["details"] == {"missed": 2}
        try:
            urllib.request.urlopen(base + "/api/result?k=t&name=bad&status=pass"); assert False
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        server.shutdown(); server.server_close()


def test_pin_join_flow(tmp_path):
    p = make_report(tmp_path)
    server = webtests.make_server(p, port=0, host="127.0.0.1", token="t")
    t = threading.Thread(target=server.serve_forever, daemon=True); t.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        html = urllib.request.urlopen(base + "/").read().decode()
        assert "6-digit code" in html
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k): return None
        opener = urllib.request.build_opener(NoRedirect)
        try:
            opener.open(base + f"/join?pin={server.pin}"); assert False
        except urllib.error.HTTPError as e:
            assert e.code == 302 and e.headers["Location"] == "/?k=t"
        for _ in range(5):
            try: opener.open(base + "/join?pin=000000"); assert False
            except urllib.error.HTTPError as e: assert e.code == 403
        try: opener.open(base + f"/join?pin={server.pin}"); assert False
        except urllib.error.HTTPError as e: assert e.code == 403   # locked after 5 wrong codes
    finally:
        server.shutdown(); server.server_close()


def test_https_server_survives_a_stalled_connection(tmp_path, monkeypatch):
    """Safari holds a half-open connection during the certificate warning; others must still be served."""
    import socket, ssl
    monkeypatch.setattr(lan, "CERT_DIR", tmp_path / "certs")
    p = make_report(tmp_path)
    import pytest
    try:
        server = webtests.make_server(p, port=0, host="127.0.0.1", token="t", https=True, ip="127.0.0.1")
    except webtests.HttpsUnavailable:
        pytest.skip("openssl not available")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    silent = socket.create_connection(("127.0.0.1", server.server_port))   # never starts the handshake
    try:
        ctx = ssl._create_unverified_context()
        body = urllib.request.urlopen(f"https://127.0.0.1:{server.server_port}/api/state?k=t", context=ctx, timeout=5).read()
        assert json.loads(body)["web_tests"]
    finally:
        silent.close(); server.shutdown(); server.server_close()


def test_https_is_never_silently_downgraded(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(webtests, "self_signed_cert", lambda ip: None)     # as if openssl were missing
    with pytest.raises(webtests.HttpsUnavailable):
        webtests.make_server(make_report(tmp_path), port=0, host="127.0.0.1", https=True, ip="127.0.0.1")


def _serving(tmp_path, **kw):
    server = webtests.make_server(make_report(tmp_path), port=0, host="127.0.0.1", token="t", **kw)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _status(req):
    import urllib.error
    try:
        return urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:      # connection refused / reset under load: no status
        return None


def test_post_body_is_capped_and_never_read_without_the_token(tmp_path):
    server, base = _serving(tmp_path)
    try:
        import socket   # announce an oversized body without sending it: the server must answer 400 and not wait for it
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as c:
            c.sendall(f"POST /api/result?k=t HTTP/1.1\r\nHost: x\r\nContent-Length: {webtests.MAX_BODY_BYTES + 1}\r\n\r\n".encode())
            assert c.recv(64).startswith(b"HTTP/1.1 400")
        assert _status(urllib.request.Request(base + "/api/result?k=wrong", data=b"{}", method="POST")) == 403
        ok = urllib.request.Request(base + "/api/result?k=t", data=json.dumps({"name": "display", "status": "pass"}).encode(), method="POST")
        assert _status(ok) == 200
    finally:
        server.shutdown(); server.server_close()


def test_pin_locks_after_the_limit_even_with_parallel_guesses(tmp_path):
    server, base = _serving(tmp_path)
    wrong = "000000" if server.pin != "000000" else "111111"
    try:
        threads = [threading.Thread(target=_status, args=(base + f"/join?pin={wrong}",)) for _ in range(30)]
        [t.start() for t in threads]; [t.join() for t in threads]
        assert server.RequestHandlerClass.pin_failures == webtests.PIN_MAX_FAILURES      # counted exactly, not 30
        assert _status(base + f"/join?pin={server.pin}") == 403                          # locked: even the right code is refused
    finally:
        server.shutdown(); server.server_close()


def test_load_test_refuses_early_on_a_nearly_full_battery(tmp_path, monkeypatch):
    full = {"voltage_mv": 4356, "current_ma": 300, "charge_pct": 97, "charging": True, "gauge_update": 1}
    assert battery_load.too_full_to_measure(full) and not battery_load.too_full_to_measure({**full, "charge_pct": 46})
    assert not battery_load.too_full_to_measure({**full, "charging": False}) and not battery_load.too_full_to_measure(None)
    monkeypatch.setattr(battery_load, "read_gauge", lambda: full)
    server, base = _serving(tmp_path)
    try:
        post = lambda phase: json.loads(urllib.request.urlopen(urllib.request.Request(base + f"/api/load?k=t&phase={phase}", data=b"", method="POST")).read())
        started = post("start")
        assert started["too_full"] is True and started["charge_pct"] == 97 and started["run_below_pct"] == battery_load.NEARLY_FULL_PCT
        assert post("cancel") == {"ok": True}
        assert "battery_load" not in json.loads(server.RequestHandlerClass.report_path.read_text()).get("tests", {}).get("web", {})
    finally:
        server.shutdown(); server.server_close()
