from datetime import datetime, timedelta
from pathlib import Path

from core.config import settings
from core.models import ScanItem
from core.scanners.base import BaseScanner
from core.scanners.temp_scanner import get_windows_temp_dirs, iter_with_depth

LOG_SUFFIXES = {".log", ".old", ".bak", ".tmp"}


class LogScanner(BaseScanner):
    name = "Log Files"
    category = "log"
    risk_level = "low"
    description = "Scan old local log files"
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
        min_mtime = datetime.now() - timedelta(days=settings.log_file_min_age_days)

        for root in get_log_dirs():
            if not root.exists():
                continue

            for entry in iter_with_depth(root, max_depth=settings.scan_max_depth):
                try:
                    if not entry.is_file() or not is_log_candidate(entry):
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
                        source=classify_log_source(entry),
                        scanner=self.name,
                        risk_level=self.risk_level,
                    ))
                except (OSError, PermissionError):
                    continue

        return results


Scanner = LogScanner


def get_log_dirs() -> list[Path]:
    roots = [*settings.log_dirs, *get_windows_temp_dirs()]
    deduped = []
    seen = set()

    for root in roots:
        try:
            path = Path(root).expanduser()
            key = str(path.resolve()).casefold()
        except (OSError, ValueError):
            key = str(Path(root).expanduser().absolute()).casefold()

        if key in seen:
            continue

        seen.add(key)
        deduped.append(Path(root).expanduser())

    return deduped


def is_log_candidate(path: Path) -> bool:
    name = path.name.lower()
    suffix = path.suffix.lower()
    return suffix in LOG_SUFFIXES or name.endswith(".log.1") or ".log." in name


def classify_log_source(path: Path) -> str:
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

    return "Windows"
