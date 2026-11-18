import json

import pytest

from phonecert.report import store


@pytest.fixture
def folders(tmp_path, monkeypatch):
    reports, trash = tmp_path / "reports", tmp_path / "trash"
    reports.mkdir()
    for name in ("A_1.json", "A_2.json", "nocable-x_3.json", "imei_cache.json"):
        (reports / name).write_text(json.dumps({"scanned_at": name, "device": {}, "battery": {}}))
    (reports / ".webtests.log").write_text("log")
    monkeypatch.setattr(store, "REPORTS", reports)
    monkeypatch.setattr(store, "TRASH", trash)
    return reports, trash


def names(d):
    return sorted(f.name for f in d.iterdir())


def test_delete_one_moves_it_to_the_trash(folders):
    reports, trash = folders
    assert store.delete_reports([str(reports / "A_1.json")]) == 1
    assert names(trash) == ["A_1.json"] and "A_1.json" not in names(reports) and "A_2.json" in names(reports)


def test_clear_keeps_the_imei_cache_and_other_files(folders):
    reports, trash = folders
    assert store.delete_reports(None) == 3
    assert names(reports) == [".webtests.log", "imei_cache.json"]
    assert store.list_reports() == []              # the cache file is not a scan


def test_same_name_in_trash_is_not_overwritten(folders):
    reports, trash = folders
    trash.mkdir(); (trash / "A_1.json").write_text("older")
    store.delete_reports([str(reports / "A_1.json")])
    assert names(trash) == ["A_1 1.json", "A_1.json"] and (trash / "A_1.json").read_text() == "older"


@pytest.mark.parametrize("bad", ["imei_cache.json", ".webtests.log", "../outside.json"])
def test_refuses_anything_that_is_not_a_saved_scan(folders, tmp_path, bad):
    reports, _ = folders
    (tmp_path / "outside.json").write_text("{}")
    with pytest.raises(ValueError):
        store.delete_reports([str(reports / bad)])
    assert (tmp_path / "outside.json").exists() and (reports / "imei_cache.json").exists()


def test_save_scan_never_writes_outside_reports(tmp_path, monkeypatch):
    from phonecert.report import store
    monkeypatch.setattr(store, "REPORTS", tmp_path / "reports")
    path = store.save_scan({"device": {"serial": "../../evil/x"}})
    assert path.parent == tmp_path / "reports" and path.name.startswith("evilx_")
    assert store.save_scan({"device": {"serial": "/"}}).name.startswith("unknown_")
