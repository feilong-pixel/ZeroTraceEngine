import os
from datetime import datetime, timedelta
from pathlib import Path

from core.config import settings
from core.scanners.log_scanner import LogScanner, get_log_dirs, is_log_candidate


def set_mtime(path, value: datetime) -> None:
    timestamp = value.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_log_scanner_lists_old_log_files(repo_tmp_path, monkeypatch):
    log_root = repo_tmp_path / "logs"
    log_root.mkdir()

    old_log = log_root / "old.log"
    old_log.write_text("old log", encoding="utf-8")
    set_mtime(old_log, datetime.now() - timedelta(days=8))

    recent_log = log_root / "recent.log"
    recent_log.write_text("recent log", encoding="utf-8")

    not_log = log_root / "notes.txt"
    not_log.write_text("not log", encoding="utf-8")
    set_mtime(not_log, datetime.now() - timedelta(days=8))

    monkeypatch.setattr(settings, "log_dirs", [log_root])
    monkeypatch.setattr(settings, "log_file_min_age_days", 7)
    monkeypatch.setattr(settings, "temp_dirs", [])
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    items = LogScanner().scan()

    assert [item.path for item in items] == [str(old_log)]
    assert items[0].category == "log"
    assert items[0].source == "ZeroTrace Engine"
    assert items[0].scanner == "Log Files"


def test_log_scanner_includes_temp_log_files(repo_tmp_path, monkeypatch):
    temp_root = repo_tmp_path / "Temp"
    temp_root.mkdir()

    temp_log = temp_root / "app.log.1"
    temp_log.write_text("old temp log", encoding="utf-8")
    set_mtime(temp_log, datetime.now() - timedelta(days=8))

    monkeypatch.setattr(settings, "log_dirs", [])
    monkeypatch.setattr(settings, "log_file_min_age_days", 7)
    monkeypatch.setattr(settings, "temp_dirs", [temp_root])
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    items = LogScanner().scan()

    assert [item.path for item in items] == [str(temp_log)]
    assert items[0].source == "Windows"


def test_get_log_dirs_deduplicates_config_and_temp_dirs(repo_tmp_path, monkeypatch):
    log_root = repo_tmp_path / "logs"
    log_root.mkdir()

    monkeypatch.setattr(settings, "log_dirs", [log_root])
    monkeypatch.setattr(settings, "temp_dirs", [log_root])
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    assert get_log_dirs() == [log_root]


def test_is_log_candidate_accepts_common_rotated_log_names():
    path = Path("app.log")

    assert is_log_candidate(path)
    assert is_log_candidate(path.with_name("app.log.1"))
    assert is_log_candidate(path.with_name("app.log.2026-05-04"))
    assert not is_log_candidate(path.with_name("app.txt"))
