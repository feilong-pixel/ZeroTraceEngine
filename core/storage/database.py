import sqlite3
from core.config import settings

DATA_DIR = settings.db_path.parent
DB_PATH = settings.db_path

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
