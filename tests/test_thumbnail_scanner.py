import os
from datetime import datetime, timedelta
from pathlib import Path

from core.config import settings
from core.scanners.thumbnail_scanner import (
    ThumbnailScanner,
    get_thumbnail_cache_dirs,
    is_thumbnail_cache_file,
)


def set_mtime(path, value: datetime) -> None:
    timestamp = value.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_thumbnail_scanner_lists_old_thumbcache_files(repo_tmp_path, monkeypatch):
    cache_root = repo_tmp_path / "Explorer"
    cache_root.mkdir()

    old_thumbcache = cache_root / "thumbcache_256.db"
    old_thumbcache.write_bytes(b"thumb")
    set_mtime(old_thumbcache, datetime.now() - timedelta(days=8))

    recent_iconcache = cache_root / "iconcache_32.db"
    recent_iconcache.write_bytes(b"icon")

    other_db = cache_root / "settings.db"
    other_db.write_bytes(b"db")
    set_mtime(other_db, datetime.now() - timedelta(days=8))

    monkeypatch.setattr(settings, "thumbnail_cache_dirs", [cache_root])
    monkeypatch.setattr(settings, "thumbnail_cache_min_age_days", 7)

    items = ThumbnailScanner().scan()

    assert [item.path for item in items] == [str(old_thumbcache)]
    assert items[0].category == "thumbnail"
    assert items[0].source == "Windows Explorer"
    assert items[0].scanner == "Thumbnail Cache"
    assert items[0].risk_level == "medium"


def test_thumbnail_cache_dirs_deduplicate_roots(repo_tmp_path, monkeypatch):
    cache_root = repo_tmp_path / "Explorer"
    cache_root.mkdir()

    monkeypatch.setattr(settings, "thumbnail_cache_dirs", [cache_root, cache_root])

    assert get_thumbnail_cache_dirs() == [cache_root]


def test_is_thumbnail_cache_file_matches_explorer_cache_names():
    path = Path("thumbcache_256.db")

    assert is_thumbnail_cache_file(path)
    assert is_thumbnail_cache_file(path.with_name("iconcache_32.db"))
    assert not is_thumbnail_cache_file(path.with_name("thumbcache_256.tmp"))
    assert not is_thumbnail_cache_file(path.with_name("settings.db"))
