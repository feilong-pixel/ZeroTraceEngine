import json
import sqlite3
from typing import Any

from core.storage.database import get_conn, init_db


def save_duplicate_results(groups: list[dict[str, Any]]) -> None:
    init_db()
    conn = get_conn()

    try:
        conn.execute("DELETE FROM duplicate_scan_results")
        rows = []
        for group in groups:
            group_hash = str(group.get("hash") or "")
            for file in group.get("files", []):
                path = str(file.get("path") or "").strip()
                if not path:
                    continue
                rows.append((
                    group_hash,
                    path,
                    int(file.get("size") or 0),
                    file.get("mtime"),
                    str(file.get("root") or ""),
                    str(file.get("category") or "other"),
                    str(file.get("source") or "Duplicate Scan"),
                    str(file.get("risk_level") or "low"),
                    json.dumps(file.get("risk_reasons") or []),
                    str(file.get("quick_hash") or ""),
                    str(file.get("full_hash") or group_hash),
                ))
        conn.executemany(
            """
            INSERT INTO duplicate_scan_results (
                group_hash, path, size, mtime, root, category, source, risk_level,
                risk_reasons, quick_hash, full_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def list_duplicate_results() -> list[dict[str, Any]]:
    init_db()
    conn = get_conn()
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute(
            """
            SELECT group_hash, path, size, mtime, root, category, source, risk_level,
                   risk_reasons, quick_hash, full_hash
            FROM duplicate_scan_results
            ORDER BY id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        item = dict(row)
        try:
            item["risk_reasons"] = json.loads(item.get("risk_reasons") or "[]")
        except json.JSONDecodeError:
            item["risk_reasons"] = []
        results.append(item)
    return results


def clear_duplicate_results() -> None:
    init_db()
    conn = get_conn()

    try:
        conn.execute("DELETE FROM duplicate_scan_results")
        conn.commit()
    finally:
        conn.close()
