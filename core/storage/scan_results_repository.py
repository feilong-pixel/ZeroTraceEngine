import sqlite3

from core.models import ScanItem
from core.storage.database import get_conn, init_db


def save_scan_results(items: list[ScanItem]) -> None:
    init_db()
    conn = get_conn()
    cur = conn.cursor()

    try:
        for item in items:
            cur.execute(
                """
                INSERT INTO scan_results (
                    path, size, file_type, category, source, scanner, risk_level, mtime
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.path,
                    item.size,
                    item.file_type,
                    item.category,
                    item.source,
                    item.scanner,
                    item.risk_level,
                    item.mtime.isoformat() if item.mtime else None,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def list_scan_results() -> list[dict]:
    init_db()
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT path, size, file_type, category, source, scanner, risk_level, mtime
            FROM scan_results
            ORDER BY id ASC
        """)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def clear_scan_results() -> None:
    init_db()
    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM scan_results")
        conn.commit()
    finally:
        conn.close()


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
