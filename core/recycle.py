from datetime import datetime
from pathlib import Path
from core.storage.database import get_conn, init_db
from core.utils.file_transfer import transfer_file_safe

SAFE_RESTORE_ROOTS = [Path("C:/"), Path.home()]

def is_safe_restore_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        return any(
            resolved.is_relative_to(root) for root in SAFE_RESTORE_ROOTS
        )
    except (OSError, ValueError):
        return False

def list_recycle_records():
    return _list_clean_records(active_only=True)


def list_audit_records():
    return _list_clean_records(active_only=False)


def _list_clean_records(active_only: bool):
    init_db()
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    where_clause = "WHERE restored_at IS NULL AND purged_at IS NULL" if active_only else ""

    cur.execute(f"""
        SELECT
            id,
            original_path,
            recycle_path,
            size,
            category,
            source,
            file_type,
            scanner,
            risk_level,
            hash,
            COALESCE(operation_type, 'move_to_recycle') AS action,
            deleted_at AS created_at,
            deleted_at,
            restored_at,
            purged_at
        FROM clean_log
        {where_clause}
        ORDER BY deleted_at DESC
    """)

    rows = cur.fetchall()
    conn.close()
    return rows


def restore_records(ids: list[str]):
    results = []

    for record_id in ids:
        result = restore_record(record_id)
        results.append(result)

    return results


def restore_record(record_id: str):
    init_db()
    conn = get_conn()
    conn.row_factory = _dict_factory
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM clean_log
        WHERE id = ?
    """, (record_id,))

    record = cur.fetchone()

    if not record:
        conn.close()
        return {
            "id": record_id,
            "status": "not_found",
        }

    if record["restored_at"]:
        conn.close()
        return {
            "id": record_id,
            "status": "already_restored",
        }

    if record.get("purged_at"):
        conn.close()
        return {
            "id": record_id,
            "status": "already_purged",
        }

    original = Path(record["original_path"])
    recycled = Path(record["recycle_path"])

    if not recycled.exists():
        conn.close()
        return {
            "id": record_id,
            "status": "recycle_file_missing",
        }

    if original.exists():
        conn.close()
        return {
            "id": record_id,
            "status": "original_path_exists",
        }

    if not is_safe_restore_path(original):
        conn.close()
        return {"id": record_id, "status": "unsafe_path"}

    original.parent.mkdir(parents=True, exist_ok=True)
    transfer_file_safe(recycled, original, mode="move")

    restored_at = datetime.now().isoformat(timespec="seconds")

    cur.execute("""
        UPDATE clean_log
        SET restored_at = ?
        WHERE id = ?
    """, (restored_at, record_id))

    conn.commit()
    conn.close()

    return {
        "id": record_id,
        "status": "restored",
        "restored_at": restored_at,
    }


def _dict_factory(cursor, row):
    return {
        col[0]: row[idx]
        for idx, col in enumerate(cursor.description)
    }
