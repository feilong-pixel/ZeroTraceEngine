from datetime import datetime

from core.models import CleanRecord, ScanItem
from core.services import cleanup_service


def make_item(path: str) -> ScanItem:
    return ScanItem(
        path=path,
        size=1,
        category="temp",
        source="pytest",
        scanner="UnitScanner",
    )


def make_record(path: str) -> CleanRecord:
    return CleanRecord(
        id="clean-1",
        unique_id="clean-1",
        original_path=path,
        recycle_path=f"recycle/{path}",
        size=1,
        category="temp",
        source="pytest",
        scanner="UnitScanner",
        deleted_at=datetime(2026, 5, 4, 10, 30),
    )


def test_execute_cleanup_plan_summarizes_cleaned_missing_and_locked(monkeypatch):
    items = [
        make_item("C:/tmp/clean.tmp"),
        make_item("C:/tmp/missing.tmp"),
        make_item("C:/tmp/locked.tmp"),
    ]
    discarded = []

    def fake_execute_cleanup(item):
        if item.path.endswith("missing.tmp"):
            raise FileNotFoundError(item.path)
        if item.path.endswith("locked.tmp"):
            raise PermissionError(item.path)
        return make_record(item.path)

    monkeypatch.setattr(cleanup_service, "execute_cleanup", fake_execute_cleanup)
    monkeypatch.setattr(cleanup_service, "discard_scan_result", discarded.append)
    monkeypatch.setattr(cleanup_service, "move_empty_parent_dirs_to_recycle", lambda _: [])

    result = cleanup_service.execute_cleanup_plan(items)

    assert result["ok"] is False
    assert result["cleaned_count"] == 1
    assert result["failed_count"] == 2
    assert discarded == ["C:/tmp/missing.tmp"]
    assert [failure["status"] for failure in result["failed"]] == ["missing", "locked"]
    assert result["failed"][0]["removable_from_plan"] is True
    assert result["failed"][1]["removable_from_plan"] is False
