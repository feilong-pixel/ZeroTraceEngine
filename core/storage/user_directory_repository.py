"""
Persistence layer for UserDirectoryScan results.
"""

from __future__ import annotations

import json

from core.scanners.user_directory_scanner import (
    UserDirCategorySummary,
    UserDirItem,
    UserDirScanResult,
)
from core.storage.database import get_conn

ENGINE_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def save_user_directory_scan(result: UserDirScanResult) -> int:
    """Persist a scan result and return the new scan_id."""
    conn = get_conn()
    cur = conn.cursor()

    # Delete previous scan data (keep only latest)
    cur.execute("DELETE FROM user_directory_large_files WHERE scan_id IN (SELECT scan_id FROM user_directory_scan)")
    cur.execute("DELETE FROM user_directory_summary WHERE scan_id IN (SELECT scan_id FROM user_directory_scan)")
    cur.execute("DELETE FROM user_directory_items WHERE scan_id IN (SELECT scan_id FROM user_directory_scan)")
    cur.execute("DELETE FROM user_directory_scan")

    cur.execute(
        """
        INSERT INTO user_directory_scan
            (root_path, started_at, finished_at, duration_ms,
             total_size_bytes, total_file_count, total_dir_count,
             large_file_threshold_bytes, max_concurrency, exclude_names,
             include_hidden, include_logs, engine_version)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            result.root_path,
            result.started_at,
            result.finished_at,
            result.duration_ms,
            result.total_size_bytes,
            result.total_file_count,
            result.total_dir_count,
            result.large_file_threshold_bytes,
            result.max_concurrency,
            json.dumps(result.exclude_names, ensure_ascii=False),
            int(result.include_hidden),
            int(result.include_logs),
            result.engine_version,
        ),
    )
    scan_id: int = cur.lastrowid  # type: ignore[assignment]

    cur.executemany(
        """
        INSERT INTO user_directory_items
            (scan_id, path, type, category, size_bytes, file_count,
             last_modified, depth, is_hidden, is_symlink, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                scan_id,
                item.path,
                item.type,
                item.category,
                item.size_bytes,
                item.file_count,
                item.last_modified,
                item.depth,
                int(item.is_hidden),
                int(item.is_symlink),
                ",".join(item.notes) if item.notes else None,
            )
            for item in result.items
        ],
    )

    cur.executemany(
        """
        INSERT INTO user_directory_summary (scan_id, category, size_bytes, item_count)
        VALUES (?,?,?,?)
        """,
        [
            (scan_id, s.category, s.size_bytes, s.item_count)
            for s in result.summary.values()
        ],
    )

    # Large files follow the scan threshold, so persisted summaries stay aligned
    # if the threshold becomes user-configurable later.
    large_files = [
        i for i in result.items
        if i.type == "File" and i.size_bytes >= result.large_file_threshold_bytes
    ]
    if large_files:
        cur.executemany(
            """
            INSERT INTO user_directory_large_files (scan_id, path, size_bytes, last_modified)
            VALUES (?,?,?,?)
            """,
            [(scan_id, f.path, f.size_bytes, f.last_modified) for f in large_files],
        )

    conn.commit()
    conn.close()
    return scan_id


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def load_user_directory_scan_meta() -> dict | None:
    """Return the most recent scan header row, or None if no scan exists."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT scan_id, root_path, started_at, finished_at, duration_ms,
               total_size_bytes, total_file_count, total_dir_count,
               large_file_threshold_bytes, max_concurrency, exclude_names,
               include_hidden, include_logs, engine_version
        FROM user_directory_scan
        ORDER BY scan_id DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "scan_id": row[0],
        "root_path": row[1],
        "started_at": row[2],
        "finished_at": row[3],
        "duration_ms": row[4],
        "total_size_bytes": row[5],
        "total_file_count": row[6],
        "total_dir_count": row[7],
        "large_file_threshold_bytes": row[8] or 100 * 1024 * 1024,
        "max_concurrency": row[9] or 4,
        "exclude_names": json.loads(row[10]) if row[10] else [".git", "node_modules"],
        "include_hidden": bool(row[11]),
        "include_logs": bool(row[12]),
        "engine_version": row[13],
    }


def load_user_directory_items(
    scan_id: int,
    category: str | None = None,
    item_type: str | None = None,
    search: str | None = None,
    min_size: int | None = None,
    order_by: str = "size_bytes",
    order_dir: str = "DESC",
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()

    safe_order = "size_bytes" if order_by not in {"size_bytes", "last_modified", "path", "depth"} else order_by
    safe_dir = "ASC" if order_dir.upper() == "ASC" else "DESC"

    clauses = ["scan_id = ?"]
    params: list = [scan_id]

    if category:
        clauses.append("category = ?")
        params.append(category)
    if item_type:
        clauses.append("type = ?")
        params.append(item_type)
    if search:
        clauses.append("path LIKE ?")
        params.append(f"%{search}%")
    if min_size is not None:
        clauses.append("size_bytes >= ?")
        params.append(min_size)

    where = " AND ".join(clauses)
    page_clause = ""
    if limit > 0:
        page_clause = "LIMIT ? OFFSET ?"
        params += [limit, offset]

    cur.execute(
        f"""
        SELECT item_id, path, type, category, size_bytes, file_count,
               last_modified, depth, is_hidden, is_symlink, notes
        FROM user_directory_items
        WHERE {where}
        ORDER BY {safe_order} {safe_dir}
        {page_clause}
        """,
        params,
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "item_id": r[0],
            "path": r[1],
            "type": r[2],
            "category": r[3],
            "size_bytes": r[4],
            "file_count": r[5],
            "last_modified": r[6],
            "depth": r[7],
            "is_hidden": bool(r[8]),
            "is_symlink": bool(r[9]),
            "notes": r[10].split(",") if r[10] else [],
        }
        for r in rows
    ]


def load_user_directory_top_items(scan_id: int, limit: int = 16) -> list[dict]:
    return load_user_directory_items(
        scan_id=scan_id,
        order_by="size_bytes",
        order_dir="DESC",
        limit=limit,
        offset=0,
    )


def _build_user_directory_item_filters(
    scan_id: int,
    category: str | None = None,
    item_type: str | None = None,
    search: str | None = None,
    min_size: int | None = None,
) -> tuple[str, list]:
    clauses = ["scan_id = ?"]
    params: list = [scan_id]

    if category:
        clauses.append("category = ?")
        params.append(category)
    if item_type:
        clauses.append("type = ?")
        params.append(item_type)
    if search:
        clauses.append("path LIKE ?")
        params.append(f"%{search}%")
    if min_size is not None:
        clauses.append("size_bytes >= ?")
        params.append(min_size)

    return " AND ".join(clauses), params


def count_user_directory_items(
    scan_id: int,
    category: str | None = None,
    item_type: str | None = None,
    search: str | None = None,
    min_size: int | None = None,
) -> int:
    conn = get_conn()
    cur = conn.cursor()
    where, params = _build_user_directory_item_filters(
        scan_id=scan_id,
        category=category,
        item_type=item_type,
        search=search,
        min_size=min_size,
    )
    cur.execute(f"SELECT COUNT(*) FROM user_directory_items WHERE {where}", params)
    n = cur.fetchone()[0]
    conn.close()
    return n


def count_user_directory_items_by_size(scan_id: int, min_size: int, item_type: str | None = None) -> int:
    conn = get_conn()
    cur = conn.cursor()
    clauses = ["scan_id = ?", "size_bytes >= ?"]
    params: list = [scan_id, min_size]
    if item_type:
        clauses.append("type = ?")
        params.append(item_type)
    cur.execute(f"SELECT COUNT(*) FROM user_directory_items WHERE {' AND '.join(clauses)}", params)
    n = cur.fetchone()[0]
    conn.close()
    return n


def load_user_directory_summary(scan_id: int) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT category, size_bytes, item_count
        FROM user_directory_summary
        WHERE scan_id = ?
        ORDER BY size_bytes DESC
        """,
        (scan_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"category": r[0], "size_bytes": r[1], "item_count": r[2]} for r in rows]


def load_user_directory_large_files(scan_id: int, limit: int = 50) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT path, size_bytes, last_modified
        FROM user_directory_large_files
        WHERE scan_id = ?
        ORDER BY size_bytes DESC
        LIMIT ?
        """,
        (scan_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"path": r[0], "size_bytes": r[1], "last_modified": r[2]} for r in rows]


def clear_user_directory_scan() -> None:
    conn = get_conn()
    conn.execute("DELETE FROM user_directory_large_files")
    conn.execute("DELETE FROM user_directory_summary")
    conn.execute("DELETE FROM user_directory_items")
    conn.execute("DELETE FROM user_directory_scan")
    conn.commit()
    conn.close()
