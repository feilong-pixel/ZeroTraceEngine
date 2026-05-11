from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.services.duplicate_service import (
    clear_duplicate_scan_results,
    create_duplicate_cleanup_plan,
    load_saved_duplicate_scan_results,
    scan_duplicates,
)
from core.storage.settings_repository import get_setting, set_setting

from .index_router import STATIC_DIR


router = APIRouter()
DUPLICATES_PAGE = STATIC_DIR / "duplicates.html"
DUPLICATE_ROOTS_SETTING_KEY = "duplicates.roots"


class DuplicateScanPayload(BaseModel):
    roots: list[str]


class DuplicatePlanPayload(BaseModel):
    paths: list[str]


class DuplicateRootsPayload(BaseModel):
    roots: list[str]


@router.get("/duplicates")
async def duplicates_page() -> FileResponse:
    return FileResponse(DUPLICATES_PAGE)


@router.get("/duplicates/roots")
def duplicate_roots() -> dict[str, Any]:
    roots = get_setting(DUPLICATE_ROOTS_SETTING_KEY, [])
    if not isinstance(roots, list):
        roots = []
    return {"ok": True, "roots": [str(root) for root in roots if str(root).strip()]}


@router.post("/duplicates/roots")
def duplicate_save_roots(payload: DuplicateRootsPayload) -> dict[str, Any]:
    roots = list(dict.fromkeys(str(root).strip() for root in payload.roots if str(root).strip()))
    set_setting(DUPLICATE_ROOTS_SETTING_KEY, roots)
    return {"ok": True, "roots": roots}


@router.post("/duplicates/scan")
def duplicate_scan(payload: DuplicateScanPayload) -> dict[str, Any]:
    try:
        return scan_duplicates(payload.roots)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/duplicates/results")
def duplicate_results() -> dict[str, Any]:
    return load_saved_duplicate_scan_results()


@router.post("/duplicates/results/clear")
def duplicate_clear_results() -> dict[str, Any]:
    return clear_duplicate_scan_results()


@router.post("/duplicates/createPlan")
def duplicate_create_plan(payload: DuplicatePlanPayload) -> dict[str, Any]:
    try:
        return create_duplicate_cleanup_plan(payload.paths)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
