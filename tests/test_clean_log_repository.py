from datetime import datetime

from core.models import CleanRecord
from core.storage.clean_log_repository import (
    get_clean_record,
    insert_clean_record,
    list_clean_records,
    mark_record_purged,
    mark_record_restored,
)
from core.storage.database import get_conn, init_db


def make_record(record_id: str) -> CleanRecord:
    return CleanRecord(
        id=record_id,
        unique_id=record_id,
        original_path=f"C:/tmp/{record_id}.tmp",
        recycle_path=f"C:/recycle/{record_id}.tmp",
        size=10,
        category="temp",
        source="pytest",
        scanner="UnitScanner",
        deleted_at=datetime(2026, 5, 4, 10, 30),
    )


def test_clean_log_repository_lists_active_and_marks_restored(isolated_db):
    init_db()
    conn = get_conn()
    try:
        cur = conn.cursor()
        insert_clean_record(cur, make_record("rec-1"))
        insert_clean_record(cur, make_record("rec-2"))
        conn.commit()
    finally:
        conn.close()

    assert [row["id"] for row in list_clean_records(active_only=True)] == ["rec-1", "rec-2"]
    assert get_clean_record("rec-1")["original_path"] == "C:/tmp/rec-1.tmp"

    mark_record_restored("rec-1", "2026-05-04T11:00:00")

    assert [row["id"] for row in list_clean_records(active_only=True)] == ["rec-2"]
    assert {row["id"] for row in list_clean_records(active_only=False)} == {"rec-1", "rec-2"}
    assert get_clean_record("rec-1")["restored_at"] == "2026-05-04T11:00:00"

    mark_record_purged("rec-2", "2026-05-04T12:00:00")

    assert list_clean_records(active_only=True) == []
    assert get_clean_record("rec-2")["purged_at"] == "2026-05-04T12:00:00"
