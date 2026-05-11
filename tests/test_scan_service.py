from core.models import ScanItem
from core.services import scan_service
from core.services import scanner_service
from core.services.scanner_service import ScanResult
from core.storage.scan_results_repository import list_scan_results, save_scan_results


def test_execute_scan_returns_scanner_reports(isolated_db, monkeypatch):
    item = ScanItem(
        path="C:/Temp/old.tmp",
        size=3,
        category="temp",
        source="pytest",
        scanner="UnitScanner",
    )

    class FakeOrchestrator:
        def run_scan(self):
            return ScanResult(
                items=[item],
                errors=[],
                scanner_reports=[{
                    "scanner": "UnitScanner",
                    "category": "temp",
                    "status": "ok",
                    "count": 1,
                    "roots": ["C:/Temp"],
                }],
            )

    monkeypatch.setattr(scan_service, "ScannerOrchestrator", FakeOrchestrator)

    result = scan_service.execute_scan()

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["items"][0]["path"] == "C:/Temp/old.tmp"
    assert result["scanner_reports"] == [{
        "scanner": "UnitScanner",
        "category": "temp",
        "status": "ok",
        "count": 1,
        "roots": ["C:/Temp"],
    }]
    assert [row["path"] for row in list_scan_results()] == ["C:/Temp/old.tmp"]


def test_clear_saved_scan_results_returns_explicit_result(isolated_db):
    save_scan_results([
        ScanItem(
            path="C:/Temp/stale.tmp",
            size=1,
            category="temp",
            source="pytest",
            scanner="UnitScanner",
        )
    ])

    result = scan_service.clear_saved_scan_results()

    assert result == {
        "ok": True,
        "cleared": "scan_results",
    }
    assert list_scan_results() == []


def test_scanner_orchestrator_isolates_scanner_errors(monkeypatch):
    item = ScanItem(
        path="C:/Temp/safe.tmp",
        size=2,
        category="temp",
        source="pytest",
        scanner="OkScanner",
    )

    class OkScanner:
        name = "OkScanner"
        category = "temp"

        def run(self):
            return [item]

        def get_scan_roots(self):
            return ["C:/Temp"]

    class BrokenScanner:
        name = "BrokenScanner"
        category = "log"

        def run(self):
            raise OSError("denied")

        def get_scan_roots(self):
            return ["C:/Logs"]

    monkeypatch.setattr(scanner_service, "SCANNERS", [OkScanner(), BrokenScanner()])

    result = scanner_service.ScannerOrchestrator().run_scan()

    assert result.items == [item]
    assert result.errors == [{"scanner": "BrokenScanner", "error": "denied"}]
    assert result.scanner_reports == [
        {
            "scanner": "OkScanner",
            "category": "temp",
            "status": "ok",
            "count": 1,
            "roots": ["C:/Temp"],
        },
        {
            "scanner": "BrokenScanner",
            "category": "log",
            "status": "error",
            "count": 0,
            "roots": ["C:/Logs"],
            "error": "denied",
        },
    ]
