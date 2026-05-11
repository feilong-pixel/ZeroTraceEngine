from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.services.app_scan_service import (
    MAX_CONCURRENCY,
    MAX_RESULT_LIMIT,
    MIN_CONCURRENCY,
    clear_app_scan_service,
    get_app_scan_drive_usage,
    get_app_scan_task,
    get_app_scan_results,
    get_app_scan_top_items,
    start_app_size_rescan_task,
    start_app_scan_task,
)
from .index_router import STATIC_DIR

router = APIRouter()
APP_SCAN_PAGE = STATIC_DIR / "app-scan.html"


class AppScanPayload(BaseModel):
    max_concurrency: int = 6


@router.get("/app-scan")
async def app_scan_page() -> FileResponse:
    return FileResponse(APP_SCAN_PAGE)


@router.post("/app-scan/scan")
def app_scan_run(payload: AppScanPayload) -> dict[str, Any]:
    return start_app_scan_task(
        max_concurrency=max(MIN_CONCURRENCY, min(payload.max_concurrency, MAX_CONCURRENCY)),
    )


@router.post("/app-scan/size-rescan")
def app_scan_size_rescan(payload: AppScanPayload) -> dict[str, Any]:
    return start_app_size_rescan_task(
        max_concurrency=max(MIN_CONCURRENCY, min(payload.max_concurrency, MAX_CONCURRENCY)),
    )


@router.get("/app-scan/scan/{task_id}")
def app_scan_status(task_id: str) -> dict[str, Any]:
    return get_app_scan_task(task_id)


@router.get("/app-scan/results")
def app_scan_results(
    source: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    min_size: Optional[int] = None,
    order_by: str = "size_bytes",
    order_dir: str = "DESC",
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    return get_app_scan_results(
        source=source,
        status=status,
        search=search,
        min_size=min_size,
        order_by=order_by,
        order_dir=order_dir,
        limit=max(0, min(limit, MAX_RESULT_LIMIT)),
        offset=max(0, offset),
    )


@router.get("/app-scan/top-items")
def app_scan_top_items(limit: int = 16) -> dict[str, Any]:
    return get_app_scan_top_items(limit=max(0, min(limit, 16)))


@router.get("/app-scan/drive-usage")
def app_scan_drive_usage() -> dict[str, Any]:
    return get_app_scan_drive_usage()


@router.delete("/app-scan/results")
def app_scan_clear() -> dict[str, Any]:
    return clear_app_scan_service()
