from core.models import ScanItem
from core.services import scan_service
from core.services.scanner_service import ScanResult


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

    assert result["count"] == 1
    assert result["scanner_reports"] == [{
        "scanner": "UnitScanner",
        "category": "temp",
        "status": "ok",
        "count": 1,
        "roots": ["C:/Temp"],
    }]
