import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "zerotrace.db"


def get_conn():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clean_log (
        id TEXT PRIMARY KEY,
        original_path TEXT NOT NULL,
        recycle_path TEXT NOT NULL,
        size INTEGER NOT NULL,
        file_type TEXT DEFAULT 'file',
        category TEXT NOT NULL,
        source TEXT NOT NULL,
        scanner TEXT NOT NULL,
        risk_level TEXT DEFAULT 'low',
        hash TEXT,
        operation_type TEXT DEFAULT 'move_to_recycle',
        deleted_at TEXT NOT NULL,
        restored_at TEXT,
        purged_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS scan_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL,
        size INTEGER NOT NULL,
        file_type TEXT DEFAULT 'file',
        category TEXT NOT NULL,
        source TEXT NOT NULL,
        scanner TEXT NOT NULL,
        risk_level TEXT DEFAULT 'low',
        mtime TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


def save_scan_results(items):
    conn = get_conn()
    cur = conn.cursor()

    for item in items:
        cur.execute(
            """
            INSERT INTO scan_results (path, size, file_type, category, source, scanner, risk_level, mtime)
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
    conn.close()


def list_scan_results():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT path, size, file_type, category, source, scanner, risk_level, mtime
        FROM scan_results
        ORDER BY id ASC
    """)
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def clear_scan_results():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM scan_results")
    conn.commit()
    conn.close()
