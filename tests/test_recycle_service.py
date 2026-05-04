from datetime import datetime

from core.models import CleanRecord
from core.services import recycle_service
from core.storage.clean_log_repository import get_clean_record, insert_clean_record
from core.storage.database import get_conn, init_db


def test_restore_record_moves_file_and_marks_record_restored(isolated_db, repo_tmp_path, monkeypatch):
    original = repo_tmp_path / "restored" / "file.txt"
    recycled = repo_tmp_path / "recycle" / "file.txt"
    recycled.parent.mkdir()
    recycled.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(recycle_service, "SAFE_RESTORE_ROOTS", [repo_tmp_path])

    record = CleanRecord(
        id="restore-1",
        unique_id="restore-1",
        original_path=str(original),
        recycle_path=str(recycled),
        size=5,
        category="temp",
        source="pytest",
        scanner="UnitScanner",
        deleted_at=datetime(2026, 5, 4, 10, 30),
    )

    init_db()
    conn = get_conn()
    try:
        cur = conn.cursor()
        insert_clean_record(cur, record)
        conn.commit()
    finally:
        conn.close()

    result = recycle_service.restore_record("restore-1")

    assert result["status"] == "restored"
    assert original.read_text(encoding="utf-8") == "hello"
    assert not recycled.exists()
    assert get_clean_record("restore-1")["restored_at"] == result["restored_at"]
