import os
from datetime import datetime, timedelta

from core.config import settings
from core.scanners.empty_scanner import (
    EmptyScanner,
    get_empty_scan_dirs,
    is_leaf_empty_dir,
)


def set_mtime(path, value: datetime) -> None:
    timestamp = value.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_empty_scanner_lists_old_empty_files_and_leaf_empty_dirs(repo_tmp_path, monkeypatch):
    root = repo_tmp_path / "Temp"
    empty_dir = root / "empty-dir"
    empty_dir.mkdir(parents=True)
    set_mtime(empty_dir, datetime.now() - timedelta(hours=25))

    empty_file = root / "empty.tmp"
    empty_file.write_text("", encoding="utf-8")
    set_mtime(empty_file, datetime.now() - timedelta(hours=25))

    non_empty_file = root / "non-empty.tmp"
    non_empty_file.write_text("data", encoding="utf-8")
    set_mtime(non_empty_file, datetime.now() - timedelta(hours=25))

    recent_empty_file = root / "recent.tmp"
    recent_empty_file.write_text("", encoding="utf-8")

    monkeypatch.setattr(settings, "empty_scan_dirs", [root])
    monkeypatch.setattr(settings, "temp_dirs", [])
    monkeypatch.setattr(settings, "log_dirs", [])
    monkeypatch.setattr(settings, "windows_update_dirs", [])
    monkeypatch.setattr(settings, "empty_item_min_age_hours", 24)
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    items = EmptyScanner().scan()

    assert {item.path for item in items} == {str(empty_dir), str(empty_file)}
    assert {item.file_type for item in items} == {"file", "folder"}
    assert {item.category for item in items} == {"empty"}


def test_empty_scanner_does_not_report_scan_root_as_empty(repo_tmp_path, monkeypatch):
    root = repo_tmp_path / "EmptyRoot"
    root.mkdir()
    set_mtime(root, datetime.now() - timedelta(hours=25))

    monkeypatch.setattr(settings, "empty_scan_dirs", [root])
    monkeypatch.setattr(settings, "temp_dirs", [])
    monkeypatch.setattr(settings, "log_dirs", [])
    monkeypatch.setattr(settings, "windows_update_dirs", [])
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    assert not is_leaf_empty_dir(root)
    assert EmptyScanner().scan() == []


def test_empty_scan_dirs_deduplicate_safe_roots(repo_tmp_path, monkeypatch):
    root = repo_tmp_path / "Temp"
    root.mkdir()

    monkeypatch.setattr(settings, "empty_scan_dirs", [root])
    monkeypatch.setattr(settings, "temp_dirs", [root])
    monkeypatch.setattr(settings, "log_dirs", [])
    monkeypatch.setattr(settings, "windows_update_dirs", [])
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    assert get_empty_scan_dirs() == [root]
