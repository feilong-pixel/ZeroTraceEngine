import os
from datetime import datetime, timedelta

from core.config import settings
from core.scanners.windows_update_scanner import (
    WindowsUpdateScanner,
    get_windows_update_dirs,
)


def set_mtime(path, value: datetime) -> None:
    timestamp = value.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_windows_update_scanner_lists_old_download_cache_files(repo_tmp_path, monkeypatch):
    update_root = repo_tmp_path / "SoftwareDistribution" / "Download"
    update_root.mkdir(parents=True)

    old_file = update_root / "old.cab"
    old_file.write_bytes(b"update")
    set_mtime(old_file, datetime.now() - timedelta(days=15))

    recent_file = update_root / "recent.cab"
    recent_file.write_bytes(b"update")

    monkeypatch.setattr(settings, "windows_update_dirs", [update_root])
    monkeypatch.setattr(settings, "windows_update_min_age_days", 14)

    items = WindowsUpdateScanner().scan()

    assert [item.path for item in items] == [str(old_file)]
    assert items[0].category == "update"
    assert items[0].source == "Windows Update"
    assert items[0].scanner == "Windows Update"
    assert items[0].risk_level == "medium"


def test_windows_update_scanner_ignores_missing_roots(repo_tmp_path, monkeypatch):
    missing_root = repo_tmp_path / "missing"

    monkeypatch.setattr(settings, "windows_update_dirs", [missing_root])

    assert WindowsUpdateScanner().scan() == []


def test_get_windows_update_dirs_deduplicates_roots(repo_tmp_path, monkeypatch):
    update_root = repo_tmp_path / "Download"
    update_root.mkdir()

    monkeypatch.setattr(settings, "windows_update_dirs", [update_root, update_root])

    assert get_windows_update_dirs() == [update_root]
