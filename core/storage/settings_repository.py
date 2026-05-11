import json
from typing import Any

from core.storage.database import get_conn, init_db


def get_setting(key: str, default: Any = None) -> Any:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()

    if row is None:
        return default
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return default


def set_setting(key: str, value: Any) -> None:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, json.dumps(value, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
