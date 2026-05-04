from datetime import datetime, timedelta
from pathlib import Path

from core.config import settings
from core.models import ScanItem
from core.scanners.base import BaseScanner
from core.scanners.temp_scanner import iter_with_depth


class WindowsUpdateScanner(BaseScanner):
    name = "Windows Update"
    category = "update"
    risk_level = "medium"
    description = "Detect old Windows Update download cache candidates"
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
        min_mtime = datetime.now() - timedelta(days=settings.windows_update_min_age_days)

        for root in get_windows_update_dirs():
            if not root.exists():
                continue

            for entry in iter_with_depth(root, max_depth=settings.scan_max_depth):
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
                        file_type="file",
                        category=self.category,
                        source="Windows Update",
                        scanner=self.name,
                        risk_level=self.risk_level,
                    ))
                except (OSError, PermissionError):
                    continue

        return results

    def get_scan_roots(self) -> list[Path]:
        return get_windows_update_dirs()


Scanner = WindowsUpdateScanner


def get_windows_update_dirs() -> list[Path]:
    roots = []
    seen = set()

    for root in settings.windows_update_dirs:
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
