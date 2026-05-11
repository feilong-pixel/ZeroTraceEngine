from core.storage import database
from core.storage.settings_repository import get_setting, set_setting


def test_settings_repository_stores_json_values(repo_tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", repo_tmp_path)
    monkeypatch.setattr(database, "DB_PATH", repo_tmp_path / "zerotrace.db")

    set_setting("duplicates.roots", ["D:/photos", "E:/backup"])

    assert get_setting("duplicates.roots") == ["D:/photos", "E:/backup"]


def test_settings_repository_updates_existing_value(repo_tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", repo_tmp_path)
    monkeypatch.setattr(database, "DB_PATH", repo_tmp_path / "zerotrace.db")

    set_setting("duplicates.roots", ["D:/old"])
    set_setting("duplicates.roots", ["D:/new"])

    assert get_setting("duplicates.roots") == ["D:/new"]
