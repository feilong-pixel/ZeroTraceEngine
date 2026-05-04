import os
from datetime import datetime, timedelta
from pathlib import Path
from .base import BaseScanner
from core.models import ScanItem
from core.config import settings

def iter_with_depth(root: Path, max_depth: int = 5):
    def _walk(path: Path, depth: int):
        if depth > max_depth:
            return
        try:
            for entry in path.iterdir():
                yield entry
                if entry.is_dir():
                    yield from _walk(entry, depth + 1)
        except (OSError, PermissionError):
            return

    yield from _walk(root, 0)

# scan Windows temp folders for files that can be safely deleted to free up disk space.
class TempScanner(BaseScanner):
    name = "Temp Files"
    category = "temp"
    risk_level = "low"
    description = "Scan Windows temporary files"
    version = "1.0"

    def __init__(self):
        super().__init__(
            name=self.name,
            category=self.category,
            risk_level=self.risk_level,
            description=self.description,
            version=self.version,
        )

    def scan(self):
        results = []
        min_mtime = datetime.now() - timedelta(hours=settings.temp_file_min_age_hours)

        for d in self.get_temp_dirs():
            if not d.exists():
                continue

            for f in iter_with_depth(d, max_depth=settings.scan_max_depth):
                try:
                    if f.is_file():
                        stat = f.stat()
                        mtime = datetime.fromtimestamp(stat.st_mtime)
                        if mtime > min_mtime:
                            continue

                        category = classify_temp_file_category(stat.st_size)

                        results.append(ScanItem(
                            path=str(f),
                            size=stat.st_size,
                            mtime=mtime,
                            file_type="file",
                            category=category,
                            source="Windows",
                            scanner=self.name,
                            risk_level=self.risk_level
                        ))

                except (OSError, PermissionError):
                    continue

        return results

    def get_temp_dirs(self):
        return get_windows_temp_dirs()

    def get_scan_roots(self) -> list[Path]:
        return self.get_temp_dirs()


Scanner = TempScanner


def classify_temp_file_category(size: int) -> str:
    return "temp"


def get_windows_temp_dirs() -> list[Path]:
    candidates = [
        *settings.temp_dirs,
        os.environ.get("TEMP"),
        os.environ.get("TMP"),
    ]
    roots = []
    seen = set()

    for candidate in candidates:
        if not candidate:
            continue

        path = Path(candidate).expanduser()
        try:
            key = str(path.resolve()).casefold()
        except (OSError, ValueError):
            key = str(path.absolute()).casefold()

        if key in seen:
            continue

        seen.add(key)
        roots.append(path)

    return roots


def is_empty_dir(path: Path) -> bool:
    if not path.is_dir():
        return False

    try:
        next(path.iterdir())
        return False
    except StopIteration:
        return True
    except (OSError, PermissionError):
        return False
