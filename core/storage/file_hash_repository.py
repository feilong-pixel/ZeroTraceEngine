import sqlite3
import time
from dataclasses import dataclass

from core.storage.database import get_conn, init_db


@dataclass(frozen=True)
class FileHashRecord:
    path: str
    size: int
    mtime: int
    quick_hash: str
    full_hash: str
    last_scanned: int
    is_existing: bool


def get_file_hash(path: str) -> FileHashRecord | None:
    init_db()
    conn = get_conn()
    conn.row_factory = sqlite3.Row

    try:
        row = conn.execute(
            """
            SELECT path, size, mtime, quick_hash, full_hash, last_scanned, is_existing
            FROM file_hashes
            WHERE path = ?
            """,
            (path,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return FileHashRecord(
        path=row["path"],
        size=int(row["size"]),
        mtime=int(row["mtime"]),
        quick_hash=row["quick_hash"],
        full_hash=row["full_hash"],
        last_scanned=int(row["last_scanned"]),
        is_existing=bool(row["is_existing"]),
    )


def upsert_file_hash(
    *,
    path: str,
    size: int,
    mtime: int,
    quick_hash: str,
    full_hash: str,
) -> FileHashRecord:
    init_db()
    last_scanned = int(time.time())
    conn = get_conn()

    try:
        conn.execute(
            """
            INSERT INTO file_hashes (
                path, size, mtime, quick_hash, full_hash, last_scanned, is_existing
            )
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(path) DO UPDATE SET
                size = excluded.size,
                mtime = excluded.mtime,
                quick_hash = excluded.quick_hash,
                full_hash = excluded.full_hash,
                last_scanned = excluded.last_scanned,
                is_existing = 1
            """,
            (path, size, mtime, quick_hash, full_hash, last_scanned),
        )
        conn.commit()
    finally:
        conn.close()

    return FileHashRecord(
        path=path,
        size=size,
        mtime=mtime,
        quick_hash=quick_hash,
        full_hash=full_hash,
        last_scanned=last_scanned,
        is_existing=True,
    )


def mark_missing_hashes(scanned_paths: set[str], roots: list[str]) -> int:
    init_db()
    conn = get_conn()

    try:
        rows = conn.execute("SELECT path FROM file_hashes WHERE is_existing = 1").fetchall()
        normalized_roots = tuple(root.rstrip("\\/") for root in roots)
        missing = [
            row[0] for row in rows
            if row[0] not in scanned_paths and is_under_any_root(row[0], normalized_roots)
        ]
        if missing:
            conn.executemany(
                "UPDATE file_hashes SET is_existing = 0, last_scanned = ? WHERE path = ?",
                [(int(time.time()), path) for path in missing],
            )
        conn.commit()
        return len(missing)
    finally:
        conn.close()


def is_under_any_root(path: str, roots: tuple[str, ...]) -> bool:
    normalized = path.rstrip("\\/").casefold()
    return any(
        normalized == root.casefold()
        or normalized.startswith(root.casefold() + "\\")
        or normalized.startswith(root.casefold() + "/")
        for root in roots
    )
