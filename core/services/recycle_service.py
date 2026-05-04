from datetime import datetime
from pathlib import Path

from core.storage.clean_log_repository import (
    get_clean_record,
    list_clean_records,
    mark_record_restored,
)
from core.utils.file_transfer import transfer_file_safe

SAFE_RESTORE_ROOTS = [Path("C:/"), Path.home()]


def is_safe_restore_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        return any(
            resolved.is_relative_to(root) for root in SAFE_RESTORE_ROOTS
        )
    except (OSError, ValueError):
        return False


def list_recycle_records() -> list[dict]:
    return list_clean_records(active_only=True)


def list_audit_records() -> list[dict]:
    return list_clean_records(active_only=False)


def restore_records(ids: list[str]) -> list[dict]:
    return [restore_record(record_id) for record_id in ids]


def restore_record(record_id: str) -> dict:
    record = get_clean_record(record_id)

    if not record:
        return {
            "id": record_id,
            "status": "not_found",
        }

    if record["restored_at"]:
        return {
            "id": record_id,
            "status": "already_restored",
        }

    if record.get("purged_at"):
        return {
            "id": record_id,
            "status": "already_purged",
        }

    original = Path(record["original_path"])
    recycled = Path(record["recycle_path"])

    if not recycled.exists():
        return {
            "id": record_id,
            "status": "recycle_file_missing",
        }

    if original.exists():
        return {
            "id": record_id,
            "status": "original_path_exists",
        }

    if not is_safe_restore_path(original):
        return {"id": record_id, "status": "unsafe_path"}

    original.parent.mkdir(parents=True, exist_ok=True)
    transfer_file_safe(recycled, original, mode="move")

    restored_at = datetime.now().isoformat(timespec="seconds")
    mark_record_restored(record_id, restored_at)

    return {
        "id": record_id,
        "status": "restored",
        "restored_at": restored_at,
    }
