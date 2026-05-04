import os
from datetime import datetime, timedelta

from core.config import settings
from core.services import cleaner_service
from core.scanners.temp_scanner import TempScanner, get_windows_temp_dirs


def set_mtime(path, value: datetime) -> None:
    timestamp = value.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_temp_scanner_skips_recent_files_and_lists_old_temp_candidates(repo_tmp_path, monkeypatch):
    temp_root = repo_tmp_path / "Temp"
    temp_root.mkdir()

    old_file = temp_root / "old.tmp"
    old_file.write_text("old", encoding="utf-8")
    set_mtime(old_file, datetime.now() - timedelta(hours=25))

    recent_file = temp_root / "recent.tmp"
    recent_file.write_text("recent", encoding="utf-8")

    monkeypatch.setattr(settings, "temp_dirs", [temp_root])
    monkeypatch.setattr(settings, "temp_file_min_age_hours", 24)
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    items = TempScanner().scan()

    assert [item.path for item in items] == [str(old_file)]
    assert items[0].category == "temp"
    assert items[0].source == "Windows"


def test_temp_scanner_metadata_is_initialized():
    scanner = TempScanner()

    assert scanner.name == "Temp Files"
    assert scanner.category == "temp"


def test_temp_scanner_does_not_list_empty_dirs(repo_tmp_path, monkeypatch):
    temp_root = repo_tmp_path / "Temp"
    empty_dir = temp_root / "old-empty"
    empty_dir.mkdir(parents=True)
    set_mtime(empty_dir, datetime.now() - timedelta(hours=25))

    monkeypatch.setattr(settings, "temp_dirs", [temp_root])
    monkeypatch.setattr(settings, "temp_file_min_age_hours", 24)
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    items = TempScanner().scan()

    assert items == []


def test_get_windows_temp_dirs_merges_config_and_environment(repo_tmp_path, monkeypatch):
    configured = repo_tmp_path / "ConfiguredTemp"
    env_temp = repo_tmp_path / "EnvTemp"
    configured.mkdir()
    env_temp.mkdir()

    monkeypatch.setattr(settings, "temp_dirs", [configured, env_temp])
    monkeypatch.setenv("TEMP", str(env_temp))
    monkeypatch.setenv("TMP", str(configured))

    roots = get_windows_temp_dirs()

    assert roots == [configured, env_temp]


def test_empty_dir_cleanup_root_uses_all_temp_roots(repo_tmp_path, monkeypatch):
    first_root = repo_tmp_path / "FirstTemp"
    env_root = repo_tmp_path / "EnvTemp"
    nested = env_root / "nested"
    nested.mkdir(parents=True)
    first_root.mkdir()

    monkeypatch.setattr(settings, "temp_dirs", [first_root])
    monkeypatch.setenv("TEMP", str(env_root))
    monkeypatch.delenv("TMP", raising=False)

    assert cleaner_service.is_under_empty_dir_cleanup_root(nested)
    assert not cleaner_service.is_under_empty_dir_cleanup_root(env_root)
