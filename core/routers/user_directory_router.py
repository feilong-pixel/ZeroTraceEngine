from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from core.services.user_directory_service import (
    MAX_RESULT_LIMIT,
    clear_user_directory_results,
    get_user_directory_scan_task,
    get_user_directory_results,
    get_user_directory_top_items,
    start_user_directory_scan_task,
)
from pydantic import BaseModel

from .index_router import STATIC_DIR

router = APIRouter()
USER_DIR_PAGE = STATIC_DIR / "user-directory.html"


class UserDirScanPayload(BaseModel):
    large_file_threshold_mb: int = 100
    max_concurrency: int = 4


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@router.get("/user-directory")
async def user_directory_page() -> FileResponse:
    return FileResponse(USER_DIR_PAGE)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

@router.post("/user-directory/scan")
def user_directory_scan(payload: UserDirScanPayload) -> dict[str, Any]:
    threshold = max(1, payload.large_file_threshold_mb) * 1024 * 1024
    return start_user_directory_scan_task(
        large_file_threshold_bytes=threshold,
        max_concurrency=max(1, min(payload.max_concurrency, 16)),
    )


@router.get("/user-directory/scan/{task_id}")
def user_directory_scan_status(task_id: str) -> dict[str, Any]:
    return get_user_directory_scan_task(task_id)


@router.get("/user-directory/results")
def user_directory_results(
    category: str | None = None,
    item_type: str | None = None,
    search: str | None = None,
    min_size_mb: float | None = None,
    order_by: str = "size_bytes",
    order_dir: str = "DESC",
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    min_size = max(0, int(min_size_mb * 1024 * 1024)) if min_size_mb is not None else None
    return get_user_directory_results(
        category=category,
        item_type=item_type,
        search=search,
        min_size=min_size,
        order_by=order_by,
        order_dir=order_dir,
        limit=max(0, min(limit, MAX_RESULT_LIMIT)),
        offset=max(0, offset),
    )


@router.get("/user-directory/top-items")
def user_directory_top_items(limit: int = 16) -> dict[str, Any]:
    return get_user_directory_top_items(limit=max(0, min(limit, 16)))


@router.post("/user-directory/results/clear")
def user_directory_clear() -> dict[str, Any]:
    return clear_user_directory_results()


@router.delete("/user-directory/results")
def user_directory_clear_legacy() -> dict[str, Any]:
    return user_directory_clear()
