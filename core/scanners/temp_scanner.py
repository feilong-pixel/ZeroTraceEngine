from datetime import datetime
from pathlib import Path
from .base import BaseScanner
from core.models import ScanItem

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

    def scan(self):
        results = []

        for d in self.get_temp_dirs():
            if not d.exists():
                continue

            for f in iter_with_depth(d, max_depth=5):
                try:
                    if f.is_file():
                        stat = f.stat()
                        category = classify_temp_file_category(stat.st_size)

                        results.append(ScanItem(
                            path=str(f),
                            size=stat.st_size,
                            mtime=datetime.fromtimestamp(stat.st_mtime),
                            file_type="file",
                            category=category,
                            source="Windows",
                            scanner=self.name,
                            risk_level=self.risk_level
                        ))

                    elif is_empty_dir(f):
                        stat = f.stat()
                        results.append(ScanItem(
                            path=str(f),
                            size=0,
                            mtime=datetime.fromtimestamp(stat.st_mtime),
                            file_type="folder",
                            category="empty",
                            source="Windows",
                            scanner=self.name,
                            risk_level=self.risk_level
                        ))

                except (OSError, PermissionError):
                    continue

        return results

    def get_temp_dirs(self):
        return [
            Path("C:/Windows/Temp"),
            Path(Path.home() / "AppData/Local/Temp")
        ]


Scanner = TempScanner


def classify_temp_file_category(size: int) -> str:
    return "empty" if size == 0 else "temp"


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
