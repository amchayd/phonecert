from phonecert.system import storage

# Real shape of `lockdown get com.apple.disk_usage` (bytes)
# Real values from an iPhone 13 128 GB, iOS 26 (10 Nov 2026)
# Settings showed "125,69 GB of 128 GB used" with iCloud Photos optimisation on.
RAW = {"TotalDiskCapacity": 128_000_000_000, "TotalDataCapacity": 120_290_508_800,
       "TotalDataAvailable": 97_210_437_632, "AmountDataAvailable": 938_442_752}


def test_marketed_capacity_rounds_to_box_size():
    assert storage.marketed_capacity_gb(127_999_201_280) == 128
    assert storage.marketed_capacity_gb(255_000_000_000) == 256
    assert storage.marketed_capacity_gb(None) is None


def test_analyse():
    r = storage.analyse(RAW)
    assert r["capacity_gb"] == 128
    assert r["total_gb"] == 128.0
    assert r["free_gb"] == 0.9
    assert r["used_gb"] == 127.1
    assert r["purgeable_gb"] == 96.3
    assert r["used_pct"] == 99


def test_falls_back_to_total_available_without_amount_key():
    r = storage.analyse({"TotalDiskCapacity": 128_000_000_000, "TotalDataAvailable": 97_210_437_632})
    assert r["free_gb"] == 97.2 and r["purgeable_gb"] == 0.0


def test_analyse_missing_keys():
    r = storage.analyse({})
    assert r["used_gb"] is None and r["used_pct"] is None and r["capacity_gb"] is None
