import uuid
from datetime import datetime
from pathlib import Path

from core.scanners.temp_scanner import get_windows_temp_dirs
from core.models import CleanRecord, ScanItem
from core.storage.clean_log_repository import (
    insert_clean_records,
    record_cleanup_and_discard_scan_result,
)
from core.utils.file_transfer import transfer_file_safe
from core.utils.recycling import generate_recycle_path

def move_to_recycle(item: ScanItem) -> CleanRecord:
    original = Path(item.path)
    if not original.exists():
        raise FileNotFoundError(item.path)

    unique_id = uuid.uuid4().hex
    target = generate_recycle_path(str(original), unique_id=unique_id)

    transfer_file_safe(original, target, mode="move")
    deleted_at = datetime.now()

    return CleanRecord(
        id=unique_id,
        unique_id=unique_id,
        original_path=str(original),
        recycle_path=str(target),
        size=item.size,
        file_type=item.file_type,
        category=item.category,
        source=item.source,
        scanner=item.scanner,
        risk_level=item.risk_level,
        hash=item.hash,
        deleted_at=deleted_at,
    )


def execute_cleanup(item: ScanItem) -> CleanRecord:
    record = move_to_recycle(item)
    record_cleanup_and_discard_scan_result(record)
    return record


def move_empty_parent_dirs_to_recycle(items: list[ScanItem]) -> list[CleanRecord]:
    records = []
    candidate_dirs = []

    for item in items:
        path = Path(item.path)
        parent = path.parent
        try:
            resolved_parent = parent.resolve()
        except OSError:
            continue

        if not is_under_empty_dir_cleanup_root(resolved_parent):
            continue

        stop_paths = get_empty_dir_stop_paths()
        while resolved_parent not in stop_paths:
            candidate_dirs.append(parent)
            parent = parent.parent
            try:
                resolved_parent = parent.resolve()
            except OSError:
                break

    for directory in sorted(set(candidate_dirs), key=lambda p: len(p.parts), reverse=True):
        if not is_recyclable_empty_dir(directory):
            continue

        source_item = next((item for item in items if Path(item.path).parent == directory), None)
        if source_item is None:
            continue

        record = move_to_recycle(ScanItem(
            path=str(directory),
            size=0,
            file_type="folder",
            category="empty",
            source=source_item.source,
            scanner=source_item.scanner,
            risk_level=source_item.risk_level,
        ))
        records.append(record)

    insert_clean_records(records)
    return records


def is_recyclable_empty_dir(directory: Path) -> bool:
    try:
        resolved = directory.resolve()
    except OSError:
        return False

    if resolved in get_empty_dir_stop_paths():
        return False
    if not directory.exists() or not directory.is_dir():
        return False

    try:
        next(directory.iterdir())
        return False
    except StopIteration:
        return True
    except (OSError, PermissionError):
        return False


def is_under_empty_dir_cleanup_root(path: Path) -> bool:
    for root in get_empty_dir_stop_paths():
        try:
            path.relative_to(root)
            return path != root
        except ValueError:
            continue
    return False


def get_empty_dir_stop_paths() -> set[Path]:
    roots = set()

    for root in get_windows_temp_dirs():
        try:
            roots.add(root.resolve())
        except (OSError, ValueError):
            continue

    return roots
