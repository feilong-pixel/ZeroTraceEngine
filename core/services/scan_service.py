from typing import Any

from core.models import ScanItem
from core.services.scanner_service import ScannerOrchestrator
from core.storage.scan_results_repository import (
    clear_scan_results,
    save_scan_results,
)


def serialize_scan_items(items: list[ScanItem]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in items]


def execute_scan() -> dict[str, Any]:
    orchestrator = ScannerOrchestrator()
    result = orchestrator.run_scan()

    clear_scan_results()
    save_scan_results(result.items)

    return {
        "ok": True,
        "count": len(result.items),
        "items": serialize_scan_items(result.items),
        "errors": result.errors,
        "scanner_reports": result.scanner_reports,
    }


def clear_saved_scan_results() -> dict[str, Any]:
    clear_scan_results()
    return {
        "ok": True,
        "cleared": "scan_results",
    }
