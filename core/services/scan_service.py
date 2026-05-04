from typing import Any

from core.services.scanner_service import ScannerOrchestrator
from core.storage.scan_results_repository import (
    clear_scan_results,
    save_scan_results,
)


def execute_scan() -> dict[str, Any]:
    orchestrator = ScannerOrchestrator()
    result = orchestrator.run_scan()

    clear_scan_results()
    save_scan_results(result.items)

    return {
        "count": len(result.items),
        "items": [item.model_dump(mode="json") for item in result.items],
        "errors": result.errors,
    }


def clear_saved_scan_results() -> dict[str, Any]:
    clear_scan_results()
    return {
        "ok": True,
        "cleared": "scan_results",
    }
