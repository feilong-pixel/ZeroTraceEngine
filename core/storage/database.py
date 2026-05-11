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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS file_hashes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL UNIQUE,
        size INTEGER NOT NULL,
        mtime INTEGER NOT NULL,
        quick_hash TEXT NOT NULL,
        full_hash TEXT NOT NULL,
        last_scanned INTEGER NOT NULL,
        is_existing INTEGER DEFAULT 1
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS duplicate_scan_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_hash TEXT NOT NULL,
        path TEXT NOT NULL UNIQUE,
        size INTEGER NOT NULL,
        mtime TEXT,
        root TEXT NOT NULL,
        category TEXT NOT NULL,
        source TEXT NOT NULL,
        risk_level TEXT DEFAULT 'low',
        risk_reasons TEXT DEFAULT '[]',
        quick_hash TEXT NOT NULL,
        full_hash TEXT NOT NULL,
        scanned_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS index_file_hash_path ON file_hashes(path)")
    cur.execute("CREATE INDEX IF NOT EXISTS index_file_hash_size ON file_hashes(size)")
    cur.execute("CREATE INDEX IF NOT EXISTS index_file_hash_quick ON file_hashes(quick_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS index_file_hash_full ON file_hashes(full_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dup_scan_hash ON duplicate_scan_results(group_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_dup_scan_path ON duplicate_scan_results(path)")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS registry_scan_results (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        risk TEXT NOT NULL DEFAULT 'Safe',
        source TEXT NOT NULL,
        hive TEXT NOT NULL,
        key_path TEXT NOT NULL,
        value_name TEXT,
        value_data TEXT,
        target_path TEXT,
        description TEXT NOT NULL,
        rule_id TEXT NOT NULL,
        confidence TEXT NOT NULL DEFAULT 'High',
        validation_status TEXT NOT NULL DEFAULT 'missing_target',
        skip_reason TEXT,
        is_system_critical INTEGER NOT NULL DEFAULT 0,
        selected INTEGER NOT NULL DEFAULT 1,
        ignored INTEGER NOT NULL DEFAULT 0,
        scanned_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS registry_cleanup_plans (
        plan_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        risk_summary TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        plan_dir TEXT NOT NULL,
        executed_at TEXT,
        restored_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS registry_cleanup_actions (
        id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL REFERENCES registry_cleanup_plans(plan_id),
        hive TEXT NOT NULL,
        key_path TEXT NOT NULL,
        value_name TEXT,
        category TEXT NOT NULL,
        risk TEXT NOT NULL,
        is_system_critical INTEGER NOT NULL DEFAULT 0,
        reg_file TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS registry_scan_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hive TEXT NOT NULL,
        key_path TEXT NOT NULL,
        scan_type TEXT NOT NULL,
        status TEXT NOT NULL,
        checked INTEGER NOT NULL DEFAULT 0,
        issues INTEGER NOT NULL DEFAULT 0,
        skipped INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        scanned_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_reg_scan_category ON registry_scan_results(category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_reg_scan_risk ON registry_scan_results(risk)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_reg_actions_plan ON registry_cleanup_actions(plan_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_reg_reports_type ON registry_scan_reports(scan_type)")

    # ------------------------------------------------------------------
    # UserDirectoryScan tables
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_directory_scan (
        scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
        root_path TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        duration_ms INTEGER,
        total_size_bytes INTEGER,
        total_file_count INTEGER,
        total_dir_count INTEGER,
        large_file_threshold_bytes INTEGER,
        max_concurrency INTEGER,
        exclude_names TEXT,
        include_hidden INTEGER NOT NULL DEFAULT 1,
        include_logs INTEGER NOT NULL DEFAULT 1,
        engine_version TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_directory_items (
        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        path TEXT NOT NULL,
        type TEXT CHECK(type IN ('File', 'Directory')),
        category TEXT NOT NULL,
        size_bytes INTEGER NOT NULL DEFAULT 0,
        file_count INTEGER NOT NULL DEFAULT 0,
        last_modified TEXT,
        depth INTEGER NOT NULL DEFAULT 0,
        is_hidden INTEGER NOT NULL DEFAULT 0,
        is_symlink INTEGER NOT NULL DEFAULT 0,
        notes TEXT,
        FOREIGN KEY(scan_id) REFERENCES user_directory_scan(scan_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_directory_summary (
        summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        size_bytes INTEGER NOT NULL DEFAULT 0,
        item_count INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(scan_id) REFERENCES user_directory_scan(scan_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_directory_large_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        path TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        last_modified TEXT,
        FOREIGN KEY(scan_id) REFERENCES user_directory_scan(scan_id)
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_udir_items_scan ON user_directory_items(scan_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_udir_items_category ON user_directory_items(category)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_udir_items_size ON user_directory_items(size_bytes)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_udir_summary_scan ON user_directory_summary(scan_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_udir_large_scan ON user_directory_large_files(scan_id)")

    # ------------------------------------------------------------------
    # AppScan tables
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS app_scans (
        scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        finished_at TEXT NOT NULL,
        duration_ms INTEGER NOT NULL,
        total_apps INTEGER NOT NULL DEFAULT 0,
        invalid_count INTEGER NOT NULL DEFAULT 0,
        total_size_bytes INTEGER NOT NULL DEFAULT 0,
        scanned_registry_keys INTEGER NOT NULL DEFAULT 0,
        scanned_directories INTEGER NOT NULL DEFAULT 0,
        summary_json TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS app_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_id INTEGER NOT NULL,
        item_id TEXT NOT NULL,
        name TEXT NOT NULL,
        version TEXT,
        publisher TEXT,
        install_path TEXT,
        size_bytes INTEGER,
        source TEXT NOT NULL,
        last_modified TEXT,
        is_valid INTEGER NOT NULL DEFAULT 1,
        is_portable INTEGER NOT NULL DEFAULT 0,
        notes TEXT,
        residual_reason TEXT,
        FOREIGN KEY(scan_id) REFERENCES app_scans(scan_id)
    )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_app_items_scan ON app_items(scan_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_app_items_source ON app_items(source)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_app_items_valid ON app_items(is_valid)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_app_items_size ON app_items(size_bytes)")

    conn.commit()
    conn.close()
