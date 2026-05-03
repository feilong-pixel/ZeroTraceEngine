from fastapi import APIRouter
from fastapi.responses import FileResponse

from .index_router import STATIC_DIR


router = APIRouter()
LOGS_PAGE = STATIC_DIR / "logs.html"


@router.get("/logs")
async def logs_page() -> FileResponse:
    return FileResponse(LOGS_PAGE)
