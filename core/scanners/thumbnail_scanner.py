from datetime import datetime, timedelta
from pathlib import Path

from core.config import settings
from core.models import ScanItem
from core.scanners.base import BaseScanner
from core.scanners.temp_scanner import iter_with_depth


class ThumbnailScanner(BaseScanner):
    name = "Thumbnail Cache"
    category = "thumbnail"
    risk_level = "medium"
    description = "Detect old Windows Explorer thumbnail cache files"
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
        min_mtime = datetime.now() - timedelta(days=settings.thumbnail_cache_min_age_days)

        for root in get_thumbnail_cache_dirs():
            try:
                if not root.exists():
                    continue
            except (OSError, PermissionError):
                continue

            for entry in iter_with_depth(root, max_depth=settings.scan_max_depth):
                try:
                    if not entry.is_file() or not is_thumbnail_cache_file(entry):
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
                        source="Windows Explorer",
                        scanner=self.name,
                        risk_level=self.risk_level,
                    ))
                except (OSError, PermissionError):
                    continue

        return results

    def get_scan_roots(self) -> list[Path]:
        return get_thumbnail_cache_dirs()


Scanner = ThumbnailScanner


def get_thumbnail_cache_dirs() -> list[Path]:
    roots = []
    seen = set()

    for root in settings.thumbnail_cache_dirs:
        path = Path(root).expanduser()
        try:
            key = str(path.resolve()).casefold()
        except (OSError, ValueError):
            key = str(path.absolute()).casefold()

        if key in seen:
            continue

        seen.add(key)
        roots.append(path)

    return roots


def is_thumbnail_cache_file(path: Path) -> bool:
    name = path.name.lower()
    return (
        path.suffix.lower() == ".db"
        and (
            name.startswith("thumbcache_")
            or name.startswith("iconcache_")
        )
    )
