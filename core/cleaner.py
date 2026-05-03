import uuid
from pathlib import Path
from datetime import datetime
from core.models import ScanItem, CleanRecord

from core.storage.database import get_conn, init_db
from core.utils.file_transfer import transfer_file_safe
from core.utils.recycling import generate_recycle_path

EMPTY_DIR_STOP_PATHS = {
    Path("C:/Windows/Temp").resolve(),
    (Path.home() / "AppData/Local/Temp").resolve(),
}

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
    init_db()
    record = move_to_recycle(item)

    conn = get_conn()
    cur = conn.cursor()

    try:
        insert_clean_record(cur, record)
        discard_scan_result(record.original_path, cur=cur)
        conn.commit()
    finally:
        conn.close()

    return record

def move_empty_parent_dirs_to_recycle(items: list[ScanItem]) -> list[CleanRecord]:
    init_db()
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

        while resolved_parent not in EMPTY_DIR_STOP_PATHS:
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

    if records:
        conn = get_conn()
        cur = conn.cursor()
        try:
            for record in records:
                insert_clean_record(cur, record)
            conn.commit()
        finally:
            conn.close()

    return records

def is_recyclable_empty_dir(directory: Path) -> bool:
    try:
        resolved = directory.resolve()
    except OSError:
        return False

    if resolved in EMPTY_DIR_STOP_PATHS:
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
    for root in EMPTY_DIR_STOP_PATHS:
        try:
            path.relative_to(root)
            return path != root
        except ValueError:
            continue
    return False

def insert_clean_record(cur, record: CleanRecord) -> None:
    deleted_at = record.deleted_at.isoformat()
    cur.execute("""
        INSERT INTO clean_log (
            id, original_path, recycle_path, size, file_type,
            category, source, scanner, risk_level, hash,
            operation_type, deleted_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        record.id,
        record.original_path,
        record.recycle_path,
        record.size,
        record.file_type,
        record.category,
        record.source,
        record.scanner,
        record.risk_level,
        record.hash,
        record.operation_type,
        deleted_at,
    ))

def discard_scan_result(path: str, cur=None) -> None:
    if cur is not None:
        cur.execute("DELETE FROM scan_results WHERE path = ?", (path,))
        return

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM scan_results WHERE path = ?", (path,))
        conn.commit()
    finally:
        conn.close()
