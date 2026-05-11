"""
AppScan repository — SQLite persistence for app scan results.
"""

from __future__ import annotations

import json
from typing import Optional

from core.app_scan_models import AppScanItem, AppScanMeta, AppScanSummary
from core.storage.database import get_conn


def _insert_app_items(cur, scan_id: int, apps: list[AppScanItem]) -> None:
    cur.executemany(
        """
        INSERT OR REPLACE INTO app_items
            (scan_id, item_id, name, version, publisher, install_path,
             size_bytes, source, last_modified, is_valid, is_portable, notes, residual_reason)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                scan_id,
                a.id,
                a.name,
                a.version,
                a.publisher,
                a.install_path,
                a.size_bytes,
                a.source,
                a.last_modified,
                1 if a.is_valid else 0,
                1 if a.is_portable else 0,
                json.dumps(a.notes),
                a.residual_reason,
            )
            for a in apps
        ],
    )


def save_app_scan(
    apps: list[AppScanItem],
    summary: AppScanSummary,
    started_at: str,
    finished_at: str,
    duration_ms: int,
) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO app_scans
                (started_at, finished_at, duration_ms, total_apps, invalid_count,
                 total_size_bytes, scanned_registry_keys, scanned_directories, summary_json)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                started_at,
                finished_at,
                duration_ms,
                summary.total_apps,
                summary.invalid_count,
                summary.total_size_bytes,
                summary.scanned_registry_keys,
                summary.scanned_directories,
                json.dumps(summary.model_dump()),
            ),
        )
        scan_id = cur.lastrowid

        _insert_app_items(cur, scan_id, apps)
        conn.commit()
        return scan_id
    finally:
        conn.close()


def update_app_scan(
    scan_id: int,
    apps: list[AppScanItem],
    summary: AppScanSummary,
    finished_at: str,
    duration_ms: int,
) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE app_scans
            SET finished_at = ?,
                duration_ms = ?,
                total_apps = ?,
                invalid_count = ?,
                total_size_bytes = ?,
                scanned_registry_keys = ?,
                scanned_directories = ?,
                summary_json = ?
            WHERE scan_id = ?
            """,
            (
                finished_at,
                duration_ms,
                summary.total_apps,
                summary.invalid_count,
                summary.total_size_bytes,
                summary.scanned_registry_keys,
                summary.scanned_directories,
                json.dumps(summary.model_dump()),
                scan_id,
            ),
        )
        cur.execute("DELETE FROM app_items WHERE scan_id = ?", (scan_id,))
        _insert_app_items(cur, scan_id, apps)
        conn.commit()
    finally:
        conn.close()


def load_app_scan_meta() -> Optional[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT scan_id, started_at, finished_at, duration_ms,
                   total_apps, invalid_count, total_size_bytes,
                   scanned_registry_keys, scanned_directories
            FROM app_scans
            ORDER BY scan_id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = ["scan_id", "started_at", "finished_at", "duration_ms",
                "total_apps", "invalid_count", "total_size_bytes",
                "scanned_registry_keys", "scanned_directories"]
        return dict(zip(cols, row))
    finally:
        conn.close()


def load_app_scan_summary(scan_id: int) -> Optional[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT summary_json FROM app_scans WHERE scan_id = ?", (scan_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except (ValueError, TypeError):
            return None
    finally:
        conn.close()


def _build_item_filters(
    scan_id: int,
    source: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    min_size: Optional[int] = None,
) -> tuple[str, list]:
    clauses = ["scan_id = ?"]
    params: list = [scan_id]

    if source:
        clauses.append("source = ?")
        params.append(source)
    if status == "valid":
        clauses.append("is_valid = 1")
    elif status == "invalid":
        clauses.append("is_valid = 0")
    elif status == "portable":
        clauses.append("is_portable = 1")
    if search:
        clauses.append("(LOWER(name) LIKE ? OR LOWER(COALESCE(install_path,'')) LIKE ?)")
        params.extend([f"%{search.lower()}%", f"%{search.lower()}%"])
    if min_size is not None:
        clauses.append("size_bytes >= ?")
        params.append(min_size)

    return " AND ".join(clauses), params


def load_app_items(
    scan_id: int,
    source: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    min_size: Optional[int] = None,
    order_by: str = "size_bytes",
    order_dir: str = "DESC",
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    allowed_order = {"size_bytes", "name", "source", "is_valid"}
    if order_by not in allowed_order:
        order_by = "size_bytes"
    order_dir = "DESC" if order_dir.upper() != "ASC" else "ASC"

    where, params = _build_item_filters(
        scan_id=scan_id,
        source=source,
        status=status,
        search=search,
        min_size=min_size,
    )
    sql = f"""
        SELECT item_id, item_id as id, name, version, publisher, install_path,
               size_bytes, source, last_modified, is_valid, is_portable, notes, residual_reason
        FROM app_items
        WHERE {where}
        ORDER BY {order_by} {order_dir} NULLS LAST
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = ["item_id", "id", "name", "version", "publisher", "install_path",
                "size_bytes", "source", "last_modified", "is_valid", "is_portable",
                "notes", "residual_reason"]
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            d["is_valid"] = bool(d["is_valid"])
            d["is_portable"] = bool(d["is_portable"])
            try:
                d["notes"] = json.loads(d["notes"]) if d["notes"] else []
            except (ValueError, TypeError):
                d["notes"] = []
            rows.append(d)
        return rows
    finally:
        conn.close()


def load_app_top_items(scan_id: int, limit: int = 16) -> list[dict]:
    return load_app_items(
        scan_id=scan_id,
        status="valid",
        order_by="size_bytes",
        order_dir="DESC",
        limit=limit,
        offset=0,
    )


def load_app_drive_usage(scan_id: int) -> dict:
    items = load_app_items(
        scan_id=scan_id,
        status="valid",
        order_by="size_bytes",
        order_dir="DESC",
        limit=100000,
        offset=0,
    )
    buckets: dict[str, int] = {}
    uncounted_count = 0
    for item in items:
        path = item.get("install_path") or ""
        size = item.get("size_bytes")
        if not path or not size:
            uncounted_count += 1
            continue
        drive = path[:2].upper() if len(path) >= 2 and path[1] == ":" else "Other"
        buckets[drive] = buckets.get(drive, 0) + int(size)

    total = sum(buckets.values())
    rows = [
        {"drive": drive, "size_bytes": size, "percent": (size / total * 100) if total else 0}
        for drive, size in sorted(buckets.items(), key=lambda row: row[1], reverse=True)
    ]
    return {"total_size_bytes": total, "drives": rows, "uncounted_count": uncounted_count}


def count_app_items(
    scan_id: int,
    source: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    min_size: Optional[int] = None,
) -> int:
    where, params = _build_item_filters(
        scan_id=scan_id,
        source=source,
        status=status,
        search=search,
        min_size=min_size,
    )
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM app_items WHERE {where}", params)
        row = cur.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def count_app_timed_out_items(scan_id: int) -> int:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM app_items
            WHERE scan_id = ?
              AND is_valid = 1
              AND install_path IS NOT NULL
              AND (
                notes LIKE '%Directory size scan timed out; partial size%'
                OR notes LIKE '%Directory size scan skipped after timeout%'
              )
            """,
            (scan_id,),
        )
        row = cur.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def clear_app_scan() -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM app_items")
        cur.execute("DELETE FROM app_scans")
        conn.commit()
    finally:
        conn.close()
