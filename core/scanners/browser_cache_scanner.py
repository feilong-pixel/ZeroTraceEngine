import os
from datetime import datetime, timedelta
from pathlib import Path

from core.config import settings
from core.models import ScanItem
from core.scanners.base import BaseScanner
from core.scanners.temp_scanner import iter_with_depth


class BrowserCacheScanner(BaseScanner):
    name = "Browser Cache"
    category = "browser_cache"
    risk_level = "low"
    description = "Scan local browser cache files"
    version = "1.0"

    def __init__(self):
        super().__init__(
            name=self.name,
            category=self.category,
            risk_level=self.risk_level,
            description=self.description,
            version=self.version,
        )

    def scan(self) -> list[ScanItem]:
        results = []
        min_mtime = datetime.now() - timedelta(hours=settings.browser_cache_min_age_hours)

        for cache_root in self.get_cache_dirs():
            if not cache_root.path.exists():
                continue

            for entry in iter_with_depth(cache_root.path, max_depth=settings.scan_max_depth):
                try:
                    if not entry.is_file():
                        continue

                    stat = entry.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    if mtime > min_mtime:
                        continue

                    results.append(ScanItem(
                        path=str(entry),
                        size=stat.st_size,
                        mtime=mtime,
                        file_type="cache",
                        category=self.category,
                        source=cache_root.source,
                        scanner=self.name,
                        risk_level=self.risk_level,
                    ))
                except (OSError, PermissionError):
                    continue

        return results

    def get_cache_dirs(self) -> list["BrowserCacheRoot"]:
        return get_browser_cache_dirs()


# Browser cache files are often locked by Chromium or system security services.
# Keep the scanner available for explicit tests/future advanced mode, but do not
# register it in the default scanner set yet.


class BrowserCacheRoot:
    def __init__(self, path: Path, source: str):
        self.path = path
        self.source = source


def get_browser_cache_dirs() -> list[BrowserCacheRoot]:
    configured_dirs = [
        BrowserCacheRoot(Path(path), "Browser")
        for path in settings.browser_cache_dirs
    ]

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return dedupe_cache_roots(configured_dirs)

    base = Path(local_app_data)
    discovered_dirs = [
        BrowserCacheRoot(base / "Google/Chrome/User Data/Default/Cache/Cache_Data", "Google Chrome"),
        BrowserCacheRoot(base / "Microsoft/Edge/User Data/Default/Cache/Cache_Data", "Microsoft Edge"),
        BrowserCacheRoot(base / "BraveSoftware/Brave-Browser/User Data/Default/Cache/Cache_Data", "Brave"),
    ]

    return dedupe_cache_roots([*configured_dirs, *discovered_dirs])


def dedupe_cache_roots(roots: list[BrowserCacheRoot]) -> list[BrowserCacheRoot]:
    deduped = []
    seen = set()

    for root in roots:
        try:
            key = str(root.path.expanduser().resolve()).casefold()
        except (OSError, ValueError):
            key = str(root.path.expanduser().absolute()).casefold()

        if key in seen:
            continue

        seen.add(key)
        deduped.append(BrowserCacheRoot(root.path.expanduser(), root.source))

    return deduped
