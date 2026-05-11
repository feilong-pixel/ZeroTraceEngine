"""
UserDirectoryScanner — deep-scans %USERPROFILE% and classifies each entry.

Architecture:
  UserDirectoryScanner
    └─ _walk()           BFS traversal with ignore rules
    └─ classifier        UserDirectoryClassifier (path → category)
    └─ _calc_dir_size()  recursive size for key directories (cached)
    └─ result            UserDirScanResult
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from core.scanners.user_dir_classifier import UserDirCategory, UserDirectoryClassifier

ENGINE_VERSION = "1.0"

# Directories to skip entirely (no entries emitted, no recursion)
_DEFAULT_EXCLUDE_NAMES: frozenset[str] = frozenset({
    "node_modules", ".git", ".svn", ".hg",
    "WindowsApps", "$Recycle.Bin", "System Volume Information",
})

@dataclass
class UserDirItem:
    path: str
    type: str           # "File" | "Directory"
    category: str       # UserDirCategory value
    size_bytes: int
    file_count: int     # meaningful for directories
    last_modified: str | None
    depth: int
    is_hidden: bool
    is_symlink: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class UserDirCategorySummary:
    category: str
    size_bytes: int = 0
    item_count: int = 0


@dataclass
class UserDirScanResult:
    root_path: str
    started_at: str
    finished_at: str
    duration_ms: int
    items: list[UserDirItem]
    summary: dict[str, UserDirCategorySummary]
    total_size_bytes: int
    total_file_count: int
    total_dir_count: int
    large_file_threshold_bytes: int
    max_concurrency: int
    exclude_names: list[str]
    include_hidden: bool = True
    include_logs: bool = True
    engine_version: str = ENGINE_VERSION


class UserDirectoryScanner:
    def __init__(
        self,
        root: Path | None = None,
        large_file_threshold_bytes: int = 100 * 1024 * 1024,
        max_concurrency: int = 4,
        exclude_names: frozenset[str] | None = None,
    ) -> None:
        self.root = root or Path(os.environ.get("USERPROFILE", Path.home()))
        self.classifier = UserDirectoryClassifier(large_file_threshold_bytes)
        self.max_concurrency = max_concurrency
        self.exclude_names: frozenset[str] = exclude_names or _DEFAULT_EXCLUDE_NAMES
        self._size_cache: dict[str, tuple[int, int]] = {}  # path → (size, file_count)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> UserDirScanResult:
        started_at = datetime.now(timezone.utc)
        items: list[UserDirItem] = []

        # Collect top-level entries and classify
        top_entries = list(self._walk_top())

        # For directories that are interesting cache dirs, compute sizes in parallel
        dirs_needing_size = [
            e for e in top_entries
            if e.type == "Directory" and e.category not in (
                UserDirCategory.USER_DATA.value, UserDirCategory.SYSTEM_TOOL_CACHE.value
            )
        ]
        self._fill_dir_sizes(dirs_needing_size)

        items.extend(top_entries)

        # Build summary
        summary: dict[str, UserDirCategorySummary] = {
            cat.value: UserDirCategorySummary(category=cat.value)
            for cat in UserDirCategory
        }
        total_files = 0
        total_dirs = 0
        for item in items:
            s = summary[item.category]
            s.size_bytes += item.size_bytes
            s.item_count += 1
            if item.type == "File":
                total_files += 1
            else:
                total_dirs += 1

        total_size = sum(s.size_bytes for s in summary.values())
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        return UserDirScanResult(
            root_path=str(self.root),
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_ms=duration_ms,
            items=items,
            summary=summary,
            total_size_bytes=total_size,
            total_file_count=total_files,
            total_dir_count=total_dirs,
            large_file_threshold_bytes=self.classifier.large_file_threshold,
            max_concurrency=self.max_concurrency,
            exclude_names=sorted(self.exclude_names),
        )

    # ------------------------------------------------------------------
    # Internal: top-level walk
    # ------------------------------------------------------------------

    def _walk_top(self) -> Iterator[UserDirItem]:
        """Emit one UserDirItem per direct child of root (dirs + files)."""
        try:
            entries = list(os.scandir(self.root))
        except PermissionError:
            return

        for entry in entries:
            try:
                name = entry.name
                if name in self.exclude_names:
                    continue
                path = Path(entry.path)
                is_symlink = entry.is_symlink()
                is_dir = entry.is_dir(follow_symlinks=False)
                stat = entry.stat(follow_symlinks=False)
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                size = 0 if is_dir else stat.st_size
                is_hidden = bool(stat.st_file_attributes & 0x2) if hasattr(stat, "st_file_attributes") else name.startswith(".")

                category = self.classifier.classify(
                    path=path,
                    root=self.root,
                    is_dir=is_dir,
                    size_bytes=size,
                )

                yield UserDirItem(
                    path=str(path),
                    type="Directory" if is_dir else "File",
                    category=category.value,
                    size_bytes=size,
                    file_count=0,
                    last_modified=mtime,
                    depth=1,
                    is_hidden=is_hidden,
                    is_symlink=is_symlink,
                    notes=[],
                )
            except (PermissionError, OSError):
                continue

    # ------------------------------------------------------------------
    # Internal: parallel directory size computation
    # ------------------------------------------------------------------

    def _fill_dir_sizes(self, dir_items: list[UserDirItem]) -> None:
        if not dir_items:
            return

        def calc(item: UserDirItem) -> tuple[UserDirItem, int, int]:
            size, count = self._dir_size(Path(item.path))
            return item, size, count

        with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
            futures = {pool.submit(calc, item): item for item in dir_items}
            for fut in as_completed(futures):
                try:
                    item, size, count = fut.result()
                    item.size_bytes = size
                    item.file_count = count
                except Exception:
                    pass

    def _dir_size(self, path: Path) -> tuple[int, int]:
        key = str(path)
        if key in self._size_cache:
            return self._size_cache[key]

        total_size = 0
        total_count = 0
        try:
            for entry in os.scandir(path):
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in self.exclude_names:
                            continue
                        sub_size, sub_count = self._dir_size(Path(entry.path))
                        total_size += sub_size
                        total_count += sub_count
                    else:
                        total_size += entry.stat(follow_symlinks=False).st_size
                        total_count += 1
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass

        self._size_cache[key] = (total_size, total_count)
        return total_size, total_count
