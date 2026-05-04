from datetime import datetime

from core.models import ScanItem
from core.storage.scan_results_repository import (
    clear_scan_results,
    discard_scan_result,
    list_scan_results,
    save_scan_results,
)


def make_item(path: str) -> ScanItem:
    return ScanItem(
        path=path,
        size=123,
        mtime=datetime(2026, 5, 4, 10, 30),
        category="temp",
        source="pytest",
        scanner="UnitScanner",
        risk_level="low",
    )


def test_scan_results_repository_roundtrip_and_discard(isolated_db):
    save_scan_results([make_item("C:/tmp/a.tmp"), make_item("C:/tmp/b.tmp")])

    rows = list_scan_results()
    assert [row["path"] for row in rows] == ["C:/tmp/a.tmp", "C:/tmp/b.tmp"]
    assert rows[0]["scanner"] == "UnitScanner"
    assert rows[0]["mtime"] == "2026-05-04T10:30:00"

    discard_scan_result("C:/tmp/a.tmp")
    assert [row["path"] for row in list_scan_results()] == ["C:/tmp/b.tmp"]

    clear_scan_results()
    assert list_scan_results() == []
