from datetime import datetime, timedelta
from pathlib import Path

from core.config import settings
from core.models import ScanItem
from core.scanners.base import BaseScanner
from core.scanners.log_scanner import get_log_dirs
from core.scanners.temp_scanner import get_windows_temp_dirs, is_empty_dir, iter_with_depth
from core.scanners.windows_update_scanner import get_windows_update_dirs


class EmptyScanner(BaseScanner):
    name = "Empty Items"
    category = "empty"
    risk_level = "low"
    description = "Scan old empty files and leaf empty folders in safe roots"
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
        min_mtime = datetime.now() - timedelta(hours=settings.empty_item_min_age_hours)

        for root in get_empty_scan_dirs():
            if not root.exists():
                continue

            for entry in iter_with_depth(root, max_depth=settings.scan_max_depth):
                try:
                    stat = entry.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    if mtime > min_mtime:
                        continue

                    if entry.is_file() and stat.st_size == 0:
                        results.append(build_empty_item(entry, mtime, "file"))
                    elif is_leaf_empty_dir(entry):
                        results.append(build_empty_item(entry, mtime, "folder"))
                except (OSError, PermissionError):
                    continue

        return results

    def get_scan_roots(self) -> list[Path]:
        return get_empty_scan_dirs()


Scanner = EmptyScanner


def build_empty_item(path: Path, mtime: datetime, file_type: str) -> ScanItem:
    return ScanItem(
        path=str(path),
        size=0,
        mtime=mtime,
        file_type=file_type,
        category="empty",
        source=classify_empty_source(path),
        scanner="Empty Items",
        risk_level="low",
    )


def get_empty_scan_dirs() -> list[Path]:
    roots = [
        *settings.empty_scan_dirs,
        *get_windows_temp_dirs(),
        *get_log_dirs(),
        *get_windows_update_dirs(),
    ]
    deduped = []
    seen = set()

    for root in roots:
        path = Path(root).expanduser()
        try:
            key = str(path.resolve()).casefold()
        except (OSError, ValueError):
            key = str(path.absolute()).casefold()

        if key in seen:
            continue

        seen.add(key)
        deduped.append(path)

    return deduped


def is_leaf_empty_dir(path: Path) -> bool:
    if not is_empty_dir(path):
        return False

    for root in get_empty_scan_dirs():
        try:
            if path.resolve() == root.resolve():
                return False
        except (OSError, ValueError):
            continue

    return True


def classify_empty_source(path: Path) -> str:
    try:
        resolved = path.resolve()
    except (OSError, ValueError):
        resolved = path.absolute()

    for root in settings.log_dirs:
        try:
            if resolved.is_relative_to(root.resolve()):
                return "ZeroTrace Engine"
        except (OSError, ValueError):
            continue

    for root in settings.windows_update_dirs:
        try:
            if resolved.is_relative_to(root.resolve()):
                return "Windows Update"
        except (OSError, ValueError):
            continue

    return "Windows"
