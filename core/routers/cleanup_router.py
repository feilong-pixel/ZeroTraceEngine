from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from core.models import ScanItem
from core.services.cleanup_service import (
    execute_cleanup_plan,
    reload_cleanup_plan_from_scan_results,
)

from .index_router import STATIC_DIR

router = APIRouter()
CLEANUP_PAGE = STATIC_DIR / "cleanup.html"


@router.get("/cleanup")
async def cleanup_page() -> FileResponse:
    return FileResponse(CLEANUP_PAGE)


@router.post("/cleanup/executePlan")
def clean(items: list[ScanItem]) -> dict[str, Any]:
    return execute_cleanup_plan(items)


@router.get("/cleanup/reloadPlanFromScanResults")
def reload_plan_from_scan_results() -> dict[str, Any]:
    return reload_cleanup_plan_from_scan_results()
