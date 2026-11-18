from phonecert.parts import inventory

TREE = {"name": "Root", "className": "IORegistryEntry", "children": [
    {"name": "D17AP", "className": "IOPlatformExpertDevice", "children": [
        {"name": "isp", "className": "AppleARMIODevice", "children": [{"name": "AppleH13CamIn", "className": "AppleH13CamIn"}]},
        {"name": "AppleAuthCPRelay", "className": "AppleAuthCPRelay"},
        {"name": "NS", "className": "AppleANS3CGv2Controller"},
        {"name": "amp", "className": "AppleCS35L27Amp"},
    ]}]}

def h(s):  # IORegistry hex-string encoding
    return {"$hex": (s.encode() + b"\x00" * 4).hex()}

PROPS = {
    "platform": {"serial-number": h("DEMO123456"), "mlb-serial-number": h("F3X2080000000000"),
                 "model-number": h("MNGK3"), "regulatory-model-number": h("A2633"),
                 "model-config": h("receiver_1=AAC;wifi_module_vendor=USI;MoPED=0x2D")},
    "battery_auth": {"AuthPassed": True, "isTrusted": True, "authErrorDescription": "AuthSuccess"},
    "camera": {"BackCameraExpected": True, "BackCameraModuleSerialNumString": "DNL14800000000000",
               "BackSuperWideCameraExpected": True, "BackSuperWideCameraModuleSerialNumString": "DNM20400000000000",
               "FrontCameraExpected": True, "FrontCameraModuleSerialNumString": "DNM20200000000000",
               "FrontIRCameraExpected": True, "FrontIRCameraModuleSerialNumString": "F8P20400000000000",
               "FrontIRStructuredLightProjectorSerialNumString": "A2C1A300000000000",
               "CmClValidationStatus": "Pass", "FCClValidationStatus": "Invalid", "SavageDATFileStatus": "Pass"},
    "face_id": {"PearlSelfTestResult": 0},
    "display": {"Panel_ID": "G9Q14500000000000+A2000000000000000201+GLD12700000000000"},
    "taptic": {"ModuleSerial": "FTN20300000000000+XPB1XX", "FirmwareVersion": "623.0"},
    "nand": {"Model Number": "APPLE SSD AP0128Z", "Serial Number": "0123456789abcdef", "Firmware Revision": "555"},
    "touch": {"Multitouch ID": 100000000000000001},
    "speaker": {"DeviceAttached": True, "AmpImonCalibrationSuccess": True},
}
BATTERY = {"Serial": "FG920330000000000", "BatteryData": {"MfgData": h("GWL15100000000000")}}


def test_find_classes_matches_generation_specific_names():
    c = inventory.find_classes(TREE)
    assert c["camera"] == "AppleH13CamIn" and c["nand"] == "AppleANS3CGv2Controller"
    assert c["speaker"] == "AppleCS35L27Amp" and "display" not in c


def test_hexstr():
    assert inventory.hexstr(h("MNGK3")) == "MNGK3"
    assert inventory.hexstr({"$hex": "ff00"}) is None
    assert inventory.hexstr("plain") == "plain" and inventory.hexstr(5) is None


def test_inventory_clean_phone():
    inv = inventory.analyse(PROPS, BATTERY)
    assert inv["logic_board"]["mlb_serial"] == "F3X2080000000000"
    assert inv["logic_board"]["wifi_module_vendor"] == "USI"
    assert inv["battery"]["auth_passed"] is True and inv["battery"]["manufacturer_data"] == "GWL15100000000000"
    assert inv["display"]["panel_serial"] == "G9Q14500000000000"
    assert set(inv["cameras"]) == {"back", "back_ultrawide", "front", "front_ir"}
    assert inv["face_id"]["self_test_result"] == 0
    assert inv["nand"]["model"] == "APPLE SSD AP0128Z"
    assert inventory.flags(inv) == []


def test_flags_failed_battery_and_missing_camera():
    props = {**PROPS, "battery_auth": {"AuthPassed": False, "isTrusted": False, "authErrorDescription": "AuthFailed"},
             "camera": {**PROPS["camera"], "BackCameraModuleSerialNumString": ""},
             "face_id": {"PearlSelfTestResult": 3}}
    f = inventory.flags(inventory.analyse(props, BATTERY))
    assert any("Battery failed" in x for x in f)
    assert any("Camera back:" in x for x in f)
    assert any("Face ID self test returned 3" in x for x in f)


def test_missing_classes_degrade_gracefully():
    inv = inventory.analyse({}, {})
    assert inv["battery"]["serial"] is None and inv["cameras"] == {}
    assert "Battery authentication not readable" in inventory.flags(inv)
