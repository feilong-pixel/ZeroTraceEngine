import os
from datetime import datetime, timedelta

from core.config import settings
from core.scanners.browser_cache_scanner import (
    BrowserCacheScanner,
    get_browser_cache_dirs,
)


def set_mtime(path, value: datetime) -> None:
    timestamp = value.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_browser_cache_scanner_lists_old_cache_files(repo_tmp_path, monkeypatch):
    cache_root = repo_tmp_path / "Chrome" / "Cache_Data"
    cache_root.mkdir(parents=True)

    old_cache = cache_root / "old-cache"
    old_cache.write_bytes(b"cache")
    set_mtime(old_cache, datetime.now() - timedelta(hours=25))

    recent_cache = cache_root / "recent-cache"
    recent_cache.write_bytes(b"cache")

    monkeypatch.setattr(settings, "browser_cache_dirs", [cache_root])
    monkeypatch.setattr(settings, "browser_cache_min_age_hours", 24)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    items = BrowserCacheScanner().scan()

    assert [item.path for item in items] == [str(old_cache)]
    assert items[0].category == "browser_cache"
    assert items[0].file_type == "cache"
    assert items[0].source == "Browser"


def test_browser_cache_scanner_discovers_chrome_and_edge_cache_dirs(repo_tmp_path, monkeypatch):
    local_app_data = repo_tmp_path / "LocalAppData"
    chrome_cache = local_app_data / "Google/Chrome/User Data/Default/Cache/Cache_Data"
    edge_cache = local_app_data / "Microsoft/Edge/User Data/Default/Cache/Cache_Data"
    chrome_code_cache = local_app_data / "Google/Chrome/User Data/Default/Code Cache/js"
    chrome_cache.mkdir(parents=True)
    edge_cache.mkdir(parents=True)
    chrome_code_cache.mkdir(parents=True)

    monkeypatch.setattr(settings, "browser_cache_dirs", [])
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    roots = [
        (root.path, root.source)
        for root in get_browser_cache_dirs()
        if root.path.exists()
    ]

    assert (chrome_cache, "Google Chrome") in roots
    assert (edge_cache, "Microsoft Edge") in roots
    assert (chrome_code_cache, "Google Chrome") not in roots


def test_browser_cache_dirs_deduplicate_config_and_discovered_paths(repo_tmp_path, monkeypatch):
    local_app_data = repo_tmp_path / "LocalAppData"
    chrome_cache = local_app_data / "Google/Chrome/User Data/Default/Cache/Cache_Data"
    chrome_cache.mkdir(parents=True)

    monkeypatch.setattr(settings, "browser_cache_dirs", [chrome_cache])
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    matching_roots = [
        root for root in get_browser_cache_dirs()
        if root.path == chrome_cache
    ]

    assert len(matching_roots) == 1
