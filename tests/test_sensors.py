import glob
import json

from phonecert.parts import sensors


def node(name, cls="IOService", children=None, state="registered, matched, active"):
    return {"name": name, "className": cls, "state": state, "children": children or []}


TREE = node("Root", children=[
    node("AppleSPU", "AppleSPU", children=[
        node("accel", "AppleSPUHIDInterface", children=[node("AppleSPUHIDDevice", "AppleSPUHIDDevice")]),
        node("gyro", "AppleSPUHIDInterface", children=[node("AppleSPUHIDDevice", "AppleSPUHIDDevice")]),
        node("als", "AppleSPUHIDInterface", children=[], state="!registered, !matched, active"),   # no driver → "found"
    ]),
    node("mt", "AppleMultitouchDevice", children=[node("uc", "AppleMultitouchDeviceUserClient")]),
    node("bluetooth", "AppleBluetoothModule", children=[node("x", "BTDebug")]),
    node("amp", "AppleCS35L27Amp", children=[node("r", "IOReportLegend")]),
])


def test_presence_from_tree():
    r = sensors.analyse(TREE)
    c = r["checks"]
    assert c["accelerometer"]["status"] == "present" and c["gyroscope"]["status"] == "present"
    assert c["ambient_light"]["status"] == "found"
    assert c["multitouch"]["status"] == "present" and c["bluetooth"]["status"] == "present"
    assert c["speaker_amp"]["status"] == "present" and c["speaker_amp"]["detail"] == "AppleCS35L27Amp"
    assert c["barometer"]["status"] == "missing" and "barometer" in r["missing"]
    assert r["total"] == len(sensors.CHECKS) and r["present"] == 5


def test_real_iphone13_tree_if_available():
    dumps = sorted(glob.glob("reports/research/*/ioreg_IOService.json"))   # local research dump, gitignored
    if not dumps:
        return
    t = open(dumps[0]).read()
    r = sensors.analyse(json.loads(t[t.find("{"):]))
    assert r["missing"] == [] and r["present"] >= 18
