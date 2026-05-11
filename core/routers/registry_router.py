from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.services.registry_cleanup_service import (
    execute_registry_plan,
    generate_registry_plan,
    get_registry_plan_detail,
    get_registry_restore_preview,
    get_registry_capabilities,
    list_registry_plans,
    restore_registry_plan,
)
from core.services.registry_scan_service import scan_registry
from core.storage.registry_scan_repository import (
    clear_registry_scan_results,
    count_registry_scan_results,
    load_registry_scan_reports,
    load_registry_scan_results,
    save_registry_scan_results,
)

from .index_router import STATIC_DIR

router = APIRouter()
REGISTRY_PAGE = STATIC_DIR / "registry.html"


class RegistryScanPayload(BaseModel):
    scope: str = "Standard"   # Standard | Extended
    mode: str  = "Safe"       # Safe | Advanced


class RegistryPlanPayload(BaseModel):
    issue_ids: list[str]


class RegistryExecutePayload(BaseModel):
    confirmed_review_action_ids: list[str] = []


class RegistryRestorePayload(BaseModel):
    confirm_overwrite: bool = False


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@router.get("/registry")
async def registry_page() -> FileResponse:
    return FileResponse(REGISTRY_PAGE)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

@router.post("/registry/scan")
def registry_scan(payload: RegistryScanPayload) -> dict[str, Any]:
    try:
        result = scan_registry(scope=payload.scope, mode=payload.mode)
        save_registry_scan_results(result["issues"], result["reports"])
        return {
            "ok":     True,
            "issues": [i.model_dump() for i in result["issues"]],
            "stats":  result["stats"],
            "reports": [r.model_dump() for r in result["reports"]],
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/registry/results")
def registry_results() -> dict[str, Any]:
    issues = load_registry_scan_results()
    reports = load_registry_scan_reports()
    from core.services.registry_scan_service import _build_stats
    return {
        "ok":     True,
        "issues": [i.model_dump() for i in issues],
        "stats":  _build_stats(issues),
        "reports": [r.model_dump() for r in reports],
        "count":  len(issues),
    }


@router.delete("/registry/results")
def registry_clear_results() -> dict[str, Any]:
    clear_registry_scan_results()
    return {"ok": True}


@router.get("/registry/capabilities")
def registry_capabilities() -> dict[str, Any]:
    return {"ok": True, **get_registry_capabilities()}


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

@router.post("/registry/plan")
def registry_create_plan(payload: RegistryPlanPayload) -> dict[str, Any]:
    try:
        return generate_registry_plan(payload.issue_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/registry/plan/{plan_id}/execute")
def registry_execute_plan(plan_id: str, payload: RegistryExecutePayload | None = None) -> dict[str, Any]:
    try:
        confirmed = payload.confirmed_review_action_ids if payload else []
        return execute_registry_plan(plan_id, confirmed_review_action_ids=confirmed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/registry/plan/{plan_id}")
def registry_plan_detail(plan_id: str) -> dict[str, Any]:
    try:
        return get_registry_plan_detail(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/registry/plan/{plan_id}/restore-preview")
def registry_restore_preview(plan_id: str) -> dict[str, Any]:
    try:
        return get_registry_restore_preview(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/registry/plan/{plan_id}/restore")
def registry_restore_plan(plan_id: str, payload: RegistryRestorePayload | None = None) -> dict[str, Any]:
    try:
        confirm_overwrite = payload.confirm_overwrite if payload else False
        return restore_registry_plan(plan_id, confirm_overwrite=confirm_overwrite)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/registry/plans")
def registry_list_plans() -> dict[str, Any]:
    return {"ok": True, "plans": list_registry_plans()}
