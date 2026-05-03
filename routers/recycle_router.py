from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from core.recycle import list_audit_records, list_recycle_records, restore_records

from .index_router import STATIC_DIR
from pydantic import BaseModel

class RestorePayload(BaseModel):
    ids: list[str]

router = APIRouter()
RECYCLE_PAGE = STATIC_DIR / "recycle.html"


@router.get("/recycle")
async def recycle_page() -> FileResponse:
    return FileResponse(RECYCLE_PAGE)


@router.get("/recycle/loadRecycleRecords")
def api_recycle() -> list[dict[str, Any]]:
    return list_recycle_records()

@router.get("/recycle/loadAuditLogs")
def api_audit_logs() -> list[dict[str, Any]]:
    return list_audit_records()

@router.post("/recycle/restore")
def api_restore(payload: RestorePayload) -> list[dict[str, Any]]:
    ids = payload.ids
    return restore_records(ids)
