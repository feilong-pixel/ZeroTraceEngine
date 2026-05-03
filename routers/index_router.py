from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"
FAVICON_FILE = BASE_DIR / "ZeroTrace.ico"

router = APIRouter()


@router.get("/")
async def index() -> FileResponse:
    return FileResponse(INDEX_FILE)


@router.get("/index.html")
async def index_html() -> FileResponse:
    return FileResponse(INDEX_FILE)


@router.get("/favicon.ico")
async def favicon() -> FileResponse:
    return FileResponse(FAVICON_FILE)
