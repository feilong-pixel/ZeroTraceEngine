from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from core.scanner import ScannerOrchestrator
from core.storage.database import (
    clear_scan_results,
    save_scan_results,
)

from .index_router import STATIC_DIR


router = APIRouter()
SCAN_PAGE = STATIC_DIR / "scan.html"


@router.get("/scan")
async def scan_page() -> FileResponse:
    return FileResponse(SCAN_PAGE)


@router.post("/scan/start")
def scan_execute() -> dict[str, Any]:
    orchestrator = ScannerOrchestrator()
    results = orchestrator.run_scan()

    clear_scan_results()
    save_scan_results(results)

    return {
        "count": len(results),
        "items": [item.dict() for item in results],
    }


@router.post("/scan/clearResults")
def api_clear_scan_results() -> dict[str, Any]:
    clear_scan_results()
    return {
        "ok": True,
        "cleared": "scan_results",
    }
