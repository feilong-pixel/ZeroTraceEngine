import sqlite3

DB_PATH = "data/zerotrace.db"

# Returns a connection to the SQLite database
def get_conn():
    return sqlite3.connect(DB_PATH)

# Initializes the database by creating the necessary tables if they do not exist
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

    _ensure_clean_log_columns(cur)
    _ensure_scan_results_columns(cur)

    conn.commit()
    conn.close()


def _ensure_clean_log_columns(cur):
    cur.execute("PRAGMA table_info(clean_log)")
    existing_columns = {row[1] for row in cur.fetchall()}

    migrations = {
        "file_type": "ALTER TABLE clean_log ADD COLUMN file_type TEXT DEFAULT 'file'",
        "scanner": "ALTER TABLE clean_log ADD COLUMN scanner TEXT DEFAULT 'UnknownScanner'",
        "risk_level": "ALTER TABLE clean_log ADD COLUMN risk_level TEXT DEFAULT 'low'",
        "hash": "ALTER TABLE clean_log ADD COLUMN hash TEXT",
        "deleted_at": "ALTER TABLE clean_log ADD COLUMN deleted_at TEXT",
        "restored_at": "ALTER TABLE clean_log ADD COLUMN restored_at TEXT",
        "purged_at": "ALTER TABLE clean_log ADD COLUMN purged_at TEXT",
    }

    for column, statement in migrations.items():
        if column not in existing_columns:
            cur.execute(statement)

    cur.execute("""
        UPDATE clean_log
        SET deleted_at = created_at
        WHERE deleted_at IS NULL
          AND created_at IS NOT NULL
    """)


def _ensure_scan_results_columns(cur):
    cur.execute("PRAGMA table_info(scan_results)")
    existing_columns = {row[1] for row in cur.fetchall()}

    if "file_type" not in existing_columns:
        cur.execute("ALTER TABLE scan_results ADD COLUMN file_type TEXT DEFAULT 'file'")


# Saves the scan results to the database by inserting records into the scan_results table
def save_scan_results(items):
    conn = get_conn()
    cur = conn.cursor()

    for item in items:
        cur.execute("""
            INSERT INTO scan_results (path, size, file_type, category, source, scanner, risk_level, mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.path,
            item.size,
            item.file_type,
            item.category,
            item.source,
            item.scanner,
            item.risk_level,
            item.mtime.isoformat() if item.mtime else None
        ))

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
