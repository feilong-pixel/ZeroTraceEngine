from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from core.cleaner import discard_scan_result, execute_cleanup, move_empty_parent_dirs_to_recycle
from core.models import ScanItem

from core.storage.database import list_scan_results

from .index_router import STATIC_DIR

router = APIRouter()
CLEANUP_PAGE = STATIC_DIR / "cleanup.html"


@router.get("/cleanup")
async def cleanup_page() -> FileResponse:
    return FileResponse(CLEANUP_PAGE)


@router.post("/cleanup/executePlan")
def clean(items: list[ScanItem]) -> dict[str, Any]:
    cleaned = []
    failed = []

    for item in items:
        try:
            cleaned.append(execute_cleanup(item).model_dump(mode="json"))
        except FileNotFoundError as error:
            discard_scan_result(item.path)
            failed.append({
                "path": item.path,
                "status": "missing",
                "message": str(error),
                "removable_from_plan": True,
            })
        except PermissionError as error:
            failed.append({
                "path": item.path,
                "status": "locked",
                "message": str(error),
                "removable_from_plan": False,
            })
        except OSError as error:
            failed.append({
                "path": item.path,
                "status": "move_failed",
                "message": str(error),
                "removable_from_plan": False,
            })

    if cleaned:
        moved_paths = {Path(record["original_path"]) for record in cleaned}
        cleaned_dirs = move_empty_parent_dirs_to_recycle([
            item for item in items
            if Path(item.path) in moved_paths
        ])
        cleaned.extend(record.model_dump(mode="json") for record in cleaned_dirs)

    return {
        "ok": len(failed) == 0,
        "cleaned_count": len(cleaned),
        "failed_count": len(failed),
        "cleaned": cleaned,
        "failed": failed,
    }

@router.get("/cleanup/reloadPlanFromScanResults")
def reload_plan_from_scan_results() -> dict[str, Any]:
    items = list_scan_results()
    return {
        "count": len(items),
        "items": items,
    }
