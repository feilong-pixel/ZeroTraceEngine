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


def test_purge_record_moves_recycled_file_to_system_recycle_and_marks_record_purged(isolated_db, repo_tmp_path, monkeypatch):
    original = repo_tmp_path / "original" / "file.txt"
    recycled = repo_tmp_path / "ZeroTraceRecycle" / "20260504" / "purge-1" / "file.txt"
    recycled.parent.mkdir(parents=True)
    recycled.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(recycle_service.settings, "recycle_root", repo_tmp_path / "ZeroTraceRecycle")
    moved_paths = []

    def fake_move_to_system_recycle(path):
        moved_paths.append(path)
        path.unlink()
        return True

    monkeypatch.setattr(recycle_service, "move_to_system_recycle", fake_move_to_system_recycle)

    record = CleanRecord(
        id="purge-1",
        unique_id="purge-1",
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

    result = recycle_service.purge_record("purge-1")

    assert result["status"] == "purged"
    assert moved_paths == [recycled]
    assert not recycled.exists()
    assert get_clean_record("purge-1")["purged_at"] == result["purged_at"]


def test_purge_record_deletes_recycled_file_on_non_windows(isolated_db, repo_tmp_path, monkeypatch):
    original = repo_tmp_path / "original" / "file.txt"
    recycled = repo_tmp_path / "ZeroTraceRecycle" / "20260504" / "purge-non-windows" / "file.txt"
    recycled.parent.mkdir(parents=True)
    recycled.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(recycle_service.settings, "recycle_root", repo_tmp_path / "ZeroTraceRecycle")
    monkeypatch.setattr(recycle_service, "is_windows", lambda: False)

    record = CleanRecord(
        id="purge-non-windows",
        unique_id="purge-non-windows",
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

    result = recycle_service.purge_record("purge-non-windows")

    assert result["status"] == "purged"
    assert not recycled.exists()
    assert get_clean_record("purge-non-windows")["purged_at"] == result["purged_at"]


def test_purge_record_rejects_paths_outside_recycle_root(isolated_db, repo_tmp_path, monkeypatch):
    recycled = repo_tmp_path / "outside.txt"
    recycled.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(recycle_service.settings, "recycle_root", repo_tmp_path / "ZeroTraceRecycle")

    record = CleanRecord(
        id="purge-unsafe",
        unique_id="purge-unsafe",
        original_path=str(repo_tmp_path / "original.txt"),
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

    result = recycle_service.purge_record("purge-unsafe")

    assert result["status"] == "unsafe_path"
    assert recycled.exists()
    assert get_clean_record("purge-unsafe")["purged_at"] is None


def test_purge_record_keeps_record_active_when_system_recycle_unavailable(isolated_db, repo_tmp_path, monkeypatch):
    original = repo_tmp_path / "original" / "file.txt"
    recycled = repo_tmp_path / "ZeroTraceRecycle" / "20260504" / "purge-unavailable" / "file.txt"
    recycled.parent.mkdir(parents=True)
    recycled.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(recycle_service.settings, "recycle_root", repo_tmp_path / "ZeroTraceRecycle")
    monkeypatch.setattr(recycle_service, "is_windows", lambda: True)
    monkeypatch.setattr(recycle_service, "move_to_system_recycle", lambda _: False)

    record = CleanRecord(
        id="purge-unavailable",
        unique_id="purge-unavailable",
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

    result = recycle_service.purge_record("purge-unavailable")

    assert result["status"] == "system_recycle_unavailable"
    assert recycled.exists()
    assert get_clean_record("purge-unavailable")["purged_at"] is None
