from phonecert.system import jailbreak

STORE = {"CFBundleDisplayName": "WhatsApp", "SignerIdentity": "Apple iPhone OS Application Signing"}


def test_clean_phone():
    r = jailbreak.analyse({"net.whatsapp.WhatsApp": STORE}, ["com.apple.app.ips"])
    assert r["verdict"] == "none" and r["user_app_count"] == 1


def test_known_jailbreak_app_is_likely():
    r = jailbreak.analyse({"org.coolstar.SileoStore": {"CFBundleDisplayName": "Sileo", "SignerIdentity": ""}}, [])
    assert r["verdict"] == "likely" and r["jailbreak_apps"] == ["Sileo (org.coolstar.sileostore)"]


def test_crash_file_of_jailbreak_daemon_is_likely():
    r = jailbreak.analyse({}, ["ellekit-2026-01-01-000000.ips"])
    assert r["verdict"] == "likely" and r["crash_hints"] == ["ellekit-2026-01-01-000000.ips"]


def test_testflight_is_legit():
    apps = {"com.gembri.app.dev": {"CFBundleDisplayName": "Gembri Dev", "SignerIdentity": "TestFlight Beta Distribution"}}
    assert jailbreak.analyse(apps, [])["verdict"] == "none"


def test_dev_signed_app_is_only_suspicious():
    apps = {"com.me.testapp": {"CFBundleDisplayName": "TestApp",
                               "SignerIdentity": "Apple Development: Someone (ABC123)"}}
    r = jailbreak.analyse(apps, [])
    assert r["verdict"] == "suspicious"
    assert r["sideloaded_apps"] == ["TestApp (com.me.testapp)"]
