from phonecert.system import profiles, sim

# Real shape from the iPhone 13: one physical SIM, registered on slot 2; slot 1 empty.
INFO = {"SIMStatus": "kCTSIMSupportSIMStatusNotInserted", "SIMTrayStatus": "kCTSIMSupportSIMTrayInsertedWithSIM",
        "SIM2IsEmbedded": False, "TelephonyCapability": True, "BasebandVersion": "5.02.02", "ActivationState": "Activated",
        "IntegratedCircuitCardIdentity2": "8900100000000000000", "InternationalMobileSubscriberIdentity2": "001010000000000",
        "CarrierBundleInfoArray": [{"CFBundleIdentifier": "com.apple.Example_xx", "MCC": "001", "MNC": "01", "Slot": "kTwo",
                                    "IntegratedCircuitCardIdentity": "8900100000000000000"}]}


def test_physical_sim_in_slot_two_is_active():
    r = sim.analyse(INFO)
    assert r["summary"] == "physical SIM in slot 2 (Example (xx))"
    assert r["active_count"] == 1 and r["esim"] is False and r["card_not_recognised"] is False
    assert r["slots"][0] == {"slot": 1, "present": False, "embedded": None, "status": "Empty", "carrier": None, "mcc": None, "mnc": None}
    assert r["slots"][1]["present"] and r["slots"][1]["carrier"] == "Example (xx)" and r["slots"][1]["mcc"] == "001"
    assert r["tray"] == "Tray in, SIM card present"
    assert "89001" not in str(r) and "0010100" not in str(r)   # personal ids never leave raw


def test_no_sim_at_all():
    r = sim.analyse({"SIMStatus": "kCTSIMSupportSIMStatusNotInserted", "SIMTrayStatus": "kCTSIMSupportSIMTrayInsertedNoSIM"})
    assert r["summary"] == "No SIM" and r["active_count"] == 0 and r["card_not_recognised"] is False


def test_card_in_tray_but_not_recognised():
    r = sim.analyse({"SIMStatus": "kCTSIMSupportSIMStatusNotInserted", "SIMTrayStatus": "kCTSIMSupportSIMTrayInsertedWithSIM"})
    assert r["card_not_recognised"] is True and r["summary"] == "No SIM"


def test_esim_only():
    r = sim.analyse({"SIMStatus": "kCTSIMSupportSIMStatusReady", "SIM1IsEmbedded": True, "IntegratedCircuitCardIdentity": "89"})
    assert r["esim"] is True and r["summary"] == "eSIM in slot 1"


def test_profiles_clean():
    r = profiles.analyse({"OrderedIdentifiers": [], "ProfileManifest": {}, "ProfileMetadata": {}})
    assert r == {"count": 0, "profiles": [], "mdm_enrolled": False, "verdict": "clean"}


def test_profiles_mdm_detected():
    raw = {"OrderedIdentifiers": ["com.acme.mdm"],
           "ProfileMetadata": {"com.acme.mdm": {"PayloadDisplayName": "Acme Device Management", "PayloadType": "com.apple.mdm"}}}
    r = profiles.analyse(raw)
    assert r["mdm_enrolled"] and r["verdict"] == "mdm" and r["profiles"] == ["Acme Device Management"]


def test_profiles_non_mdm():
    r = profiles.analyse({"OrderedIdentifiers": ["com.example.wifi"], "ProfileMetadata": {"com.example.wifi": {"PayloadDisplayName": "Office Wi-Fi"}}})
    assert r["verdict"] == "profiles" and not r["mdm_enrolled"]


def test_pin_locked_slot_one_counts_as_present():
    r = sim.analyse({"SIMStatus": "kCTSIMSupportSIMStatusPINLocked", "SIMTrayStatus": "kCTSIMSupportSIMTrayInsertedWithSIM"})
    assert r["slots"][0]["present"] is True and r["slots"][0]["status"] == "PIN locked"
    assert r["summary"] == "physical SIM in slot 1" and r["card_not_recognised"] is False


def test_unknown_status_code_is_humanised():
    assert sim._status_text("kCTSIMSupportSIMStatusSomethingNew") == "Something new"
