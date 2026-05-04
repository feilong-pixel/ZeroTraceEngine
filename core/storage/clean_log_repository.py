import sqlite3

from core.models import CleanRecord
from core.storage.database import get_conn, init_db


def dict_factory(cursor, row):
    return {
        col[0]: row[idx]
        for idx, col in enumerate(cursor.description)
    }


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


def record_cleanup_and_discard_scan_result(record: CleanRecord) -> None:
    init_db()
    conn = get_conn()
    cur = conn.cursor()

    try:
        insert_clean_record(cur, record)
        cur.execute("DELETE FROM scan_results WHERE path = ?", (record.original_path,))
        conn.commit()
    finally:
        conn.close()


def insert_clean_records(records: list[CleanRecord]) -> None:
    if not records:
        return

    init_db()
    conn = get_conn()
    cur = conn.cursor()

    try:
        for record in records:
            insert_clean_record(cur, record)
        conn.commit()
    finally:
        conn.close()


def list_clean_records(active_only: bool) -> list[dict]:
    init_db()
    conn = get_conn()
    conn.row_factory = dict_factory
    cur = conn.cursor()

    where_clause = "WHERE restored_at IS NULL AND purged_at IS NULL" if active_only else ""

    try:
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
        return cur.fetchall()
    finally:
        conn.close()


def get_clean_record(record_id: str) -> dict | None:
    init_db()
    conn = get_conn()
    conn.row_factory = dict_factory
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT *
            FROM clean_log
            WHERE id = ?
        """, (record_id,))
        return cur.fetchone()
    finally:
        conn.close()


def mark_record_restored(record_id: str, restored_at: str) -> None:
    init_db()
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE clean_log
            SET restored_at = ?
            WHERE id = ?
        """, (restored_at, record_id))
        conn.commit()
    finally:
        conn.close()


def mark_record_purged(record_id: str, purged_at: str) -> None:
    init_db()
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE clean_log
            SET purged_at = ?
            WHERE id = ?
        """, (purged_at, record_id))
        conn.commit()
    finally:
        conn.close()
