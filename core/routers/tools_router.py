from fastapi import APIRouter
from fastapi.responses import FileResponse

from .index_router import STATIC_DIR


router = APIRouter()
TOOLS_PAGE = STATIC_DIR / "tools.html"


@router.get("/tools")
async def tools_page() -> FileResponse:
    return FileResponse(TOOLS_PAGE)
