from phonecert.battery import health
from phonecert.battery.health import analyse, grade


def test_grades():
    assert grade(100) == "Excellent" and grade(95) == "Good"
    assert grade(85) == "Average" and grade(70) == "Poor" and grade(None) == "Unknown"


def test_nested_keys_ios27():
    raw = {"CurrentCapacity": 55,
           "BatteryData": {"DesignCapacity": 3582, "NominalChargeCapacity": 3200, "CycleCount": 558,
                           "Serial": "ABC"}}
    b = analyse(raw)
    assert b["health_pct"] == 89.3 and b["health_source"] == "computed"
    assert b["grade"] == "Average" and b["cycle_count"] == 558
    assert b["battery_serial"] == "ABC" and b["charge_pct"] == 55 and b["temperature_c"] is None


def test_lifetime_and_last_shutdown_iphone13():
    raw = {"BatteryData": {"DesignCapacity": 3208, "NominalChargeCapacity": 2417,
                           "LifetimeData": {"MaximumTemperature": 514, "MinimumTemperature": 35, "AverageTemperature": 25,
                                            "MaximumFCC": 3408, "MinimumFCC": 2111, "MaximumPackVoltage": 4473,
                                            "ResetCnt": 0, "TotalOperatingTime": 40951}},
           "BatteryShutdownReason": {"ShutDownTimestamp": 1794226408, "ShutDownUISoc": 0, "ShutDownVoltage": 3168,
                                     "ShutDownTemperature": 2994}}
    b = analyse(raw)
    lt = b["lifetime"]
    assert lt["max_temperature_c"] == 51.4 and lt["min_temperature_c"] == 3.5 and lt["avg_temperature_c"] == 25
    assert lt["max_full_charge_mah"] == 3408 and lt["gauge_resets"] == 0 and lt["operating_hours"] == 40951
    sd = b["last_shutdown"]
    assert sd["at"].startswith("2026-11-09") and sd["charge_pct"] == 0 and sd["voltage_mv"] == 3168
    assert sd["temperature_c"] == 29.9 and sd["unexpected"] is False


def test_shutdown_with_charge_left_is_unexpected():
    raw = {"BatteryShutdownReason": {"ShutDownTimestamp": 1794226408, "ShutDownUISoc": 35, "ShutDownVoltage": 3500}}
    assert analyse(raw)["last_shutdown"]["unexpected"] is True


def test_no_lifetime_on_ios27():
    b = analyse({"CurrentCapacity": 50, "BatteryData": {"CycleCount": 558}})
    assert b["lifetime"] == {} and b["last_shutdown"] == {}


def test_charging_states():
    from phonecert.battery.health import charging
    raw = {"IsCharging": True, "ExternalConnected": True, "Amperage": 992, "AdapterDetails": {"Watts": 15, "Description": "pd charger"},
           "ChargerData": {"NotChargingReason": 0}}
    c = charging(raw)
    assert c["status"] == "pass" and c["current_ma"] == 992 and c["adapter_watts"] == 15
    assert charging({"IsCharging": False, "ExternalConnected": True, "ChargerData": {"NotChargingReason": 5}})["status"] == "fail"
    assert charging({"IsCharging": False, "ExternalConnected": False})["status"] == "unknown"
    assert charging({"IsCharging": False, "ExternalConnected": True, "FullyCharged": True})["status"] == "pass"
    assert charging({}) == {}


def test_resistance_from_the_gauge():
    r = health.resistance({"BatteryData": {"WeightedRa": [153]}})          # iPhone 13, 75 % health, "Service"
    assert r["mohm"] == 153 and r["status"] == "high" and r["provisional"] is True
    assert health.resistance({"BatteryData": {"WeightedRa": [80]}})["status"] == "ok"
    assert health.resistance({"BatteryData": {"WeightedRa": 95}})["mohm"] == 95      # plain number, not a list
    assert health.resistance({"BatteryData": {}}) == {} and health.resistance({"BatteryData": {"WeightedRa": [0]}}) == {}
    assert health.analyse({"BatteryData": {"WeightedRa": [153], "DesignCapacity": 3208, "NominalChargeCapacity": 2405}})["resistance"]["mohm"] == 153
