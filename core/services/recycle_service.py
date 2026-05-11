import shutil
from datetime import datetime
from pathlib import Path

from core.config import settings
from core.storage.clean_log_repository import (
    get_clean_record,
    list_clean_records,
    mark_record_purged,
    mark_record_restored,
)
from core.utils.platform import is_windows
from core.utils.file_transfer import move_to_system_recycle, transfer_file_safe

SAFE_RESTORE_ROOTS = [Path("C:/"), Path.home()]


def is_safe_restore_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        return any(
            resolved.is_relative_to(root.resolve()) for root in SAFE_RESTORE_ROOTS
        )
    except (OSError, ValueError):
        return False


def list_recycle_records() -> list[dict]:
    return list_clean_records(active_only=True)


def list_audit_records() -> list[dict]:
    return list_clean_records(active_only=False)


def restore_records(ids: list[str]) -> list[dict]:
    return [restore_record(record_id) for record_id in ids]


def purge_records(ids: list[str]) -> list[dict]:
    return [purge_record(record_id) for record_id in ids]


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


def purge_record(record_id: str) -> dict:
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

    recycled = Path(record["recycle_path"])

    if not is_safe_purge_path(recycled):
        return {"id": record_id, "status": "unsafe_path"}

    if not recycled.exists():
        return {
            "id": record_id,
            "status": "recycle_file_missing",
        }

    if not dispose_recycled_path(recycled):
        return {"id": record_id, "status": "system_recycle_unavailable"}

    purged_at = datetime.now().isoformat(timespec="seconds")
    mark_record_purged(record_id, purged_at)

    return {
        "id": record_id,
        "status": "purged",
        "purged_at": purged_at,
    }


def is_safe_purge_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        recycle_root = settings.recycle_root.resolve()
        return resolved.is_relative_to(recycle_root)
    except (OSError, ValueError):
        return False


def dispose_recycled_path(path: Path) -> bool:
    if is_windows():
        return move_to_system_recycle(path)

    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True
