from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from core.services.scan_service import clear_saved_scan_results, execute_scan

from .index_router import STATIC_DIR


router = APIRouter()
SCAN_PAGE = STATIC_DIR / "scan.html"


@router.get("/scan")
async def scan_page() -> FileResponse:
    return FileResponse(SCAN_PAGE)


@router.post("/scan/start")
def start_scan() -> dict[str, Any]:
    return execute_scan()


@router.post("/scan/clearResults")
def clear_scan_results() -> dict[str, Any]:
    return clear_saved_scan_results()
