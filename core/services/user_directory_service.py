"""
UserDirectoryService — orchestrates scan execution and result retrieval.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from core.scanners.user_directory_scanner import UserDirectoryScanner
from core.storage.user_directory_repository import (
    clear_user_directory_scan,
    count_user_directory_items_by_size,
    count_user_directory_items,
    load_user_directory_items,
    load_user_directory_large_files,
    load_user_directory_scan_meta,
    load_user_directory_summary,
    load_user_directory_top_items,
    save_user_directory_scan,
)

MAX_RESULT_LIMIT = 500
DEFAULT_RESULT_LIMIT = 100
LARGE_REVIEW_THRESHOLD_BYTES = 1024 * 1024 * 1024
CLEANABLE_CATEGORIES = {"AI_TOOL_CACHE", "LOG_FILES"}
TOP_ITEMS_LIMIT = 16


@dataclass
class UserDirectoryScanTask:
    task_id: str
    started_at: str
    future: Future
    status: str = "running"
    result: dict | None = None
    error: str | None = None


_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="user-directory-scan")
_TASKS: dict[str, UserDirectoryScanTask] = {}
_TASK_LOCK = Lock()


def start_user_directory_scan_task(
    large_file_threshold_bytes: int = 100 * 1024 * 1024,
    max_concurrency: int = 4,
) -> dict:
    with _TASK_LOCK:
        for task in _TASKS.values():
            if task.status == "running" and not task.future.done():
                return {
                    "ok": True,
                    "task_id": task.task_id,
                    "status": task.status,
                    "started_at": task.started_at,
                    "reused": True,
                }

    task_id = str(uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    future = _EXECUTOR.submit(run_user_directory_scan, large_file_threshold_bytes, max_concurrency)
    task = UserDirectoryScanTask(task_id=task_id, started_at=started_at, future=future)
    with _TASK_LOCK:
        _TASKS[task_id] = task
    return {"ok": True, "task_id": task_id, "status": task.status, "started_at": started_at}


def get_user_directory_scan_task(task_id: str) -> dict:
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
    if task is None:
        return {"ok": False, "status": "missing", "error": "Scan task not found"}

    if task.future.done() and task.status == "running":
        try:
            task.result = task.future.result()
            task.status = "completed"
        except Exception as exc:  # pragma: no cover - defensive task boundary
            task.error = str(exc)
            task.status = "error"
        _trim_finished_tasks()

    response = {
        "ok": task.status != "error",
        "task_id": task.task_id,
        "status": task.status,
        "started_at": task.started_at,
    }
    if task.result is not None:
        response["result"] = task.result
    if task.error:
        response["error"] = task.error
    return response


def _trim_finished_tasks(max_finished: int = 5) -> None:
    with _TASK_LOCK:
        finished = [task for task in _TASKS.values() if task.status != "running"]
        finished.sort(key=lambda task: task.started_at, reverse=True)
        keep = {task.task_id for task in finished[:max_finished]}
        for task_id, task in list(_TASKS.items()):
            if task.status != "running" and task_id not in keep:
                del _TASKS[task_id]


def _augment_payload(meta: dict | None, summary: list[dict], payload: dict) -> dict:
    if not meta:
        payload["stats"] = None
        return payload

    scan_id = meta["scan_id"]
    total_bytes = meta.get("total_size_bytes") or 0
    cleanable_bytes = sum(
        row.get("size_bytes") or 0
        for row in summary
        if row.get("category") in CLEANABLE_CATEGORIES
    )
    over_1gb_count = count_user_directory_items_by_size(
        scan_id=scan_id,
        min_size=LARGE_REVIEW_THRESHOLD_BYTES,
    )
    threshold_bytes = meta.get("large_file_threshold_bytes") or 100 * 1024 * 1024
    exclude_names = meta.get("exclude_names") or [".git", "node_modules"]

    payload["stats"] = {
        "total_item_count": (meta.get("total_file_count") or 0) + (meta.get("total_dir_count") or 0),
        "cleanable_bytes": cleanable_bytes,
        "cleanable_percent": round((cleanable_bytes / total_bytes) * 100) if total_bytes else 0,
        "large_review_threshold_bytes": LARGE_REVIEW_THRESHOLD_BYTES,
        "large_review_item_count": over_1gb_count,
    }
    payload["scan_config"] = {
        "root_path": meta.get("root_path"),
        "large_file_threshold_bytes": threshold_bytes,
        "large_file_threshold_mb": round(threshold_bytes / 1024 / 1024),
        "max_concurrency": meta.get("max_concurrency") or 4,
        "exclude_names": exclude_names,
        "include_hidden": bool(meta.get("include_hidden", True)),
        "include_logs": bool(meta.get("include_logs", True)),
    }
    return payload


def run_user_directory_scan(
    large_file_threshold_bytes: int = 100 * 1024 * 1024,
    max_concurrency: int = 4,
) -> dict:
    scanner = UserDirectoryScanner(
        large_file_threshold_bytes=large_file_threshold_bytes,
        max_concurrency=max_concurrency,
    )
    result = scanner.run()
    scan_id = save_user_directory_scan(result)

    meta = load_user_directory_scan_meta()
    summary = load_user_directory_summary(scan_id)
    large_files = load_user_directory_large_files(scan_id, limit=20)

    return _augment_payload(meta, summary, {
        "ok": True,
        "scan_id": scan_id,
        "meta": meta,
        "summary": summary,
        "large_files": large_files,
        "item_count": count_user_directory_items(scan_id),
    })


def get_user_directory_results(
    category: str | None = None,
    item_type: str | None = None,
    search: str | None = None,
    min_size: int | None = None,
    order_by: str = "size_bytes",
    order_dir: str = "DESC",
    limit: int = 500,
    offset: int = 0,
) -> dict:
    limit = DEFAULT_RESULT_LIMIT if limit <= 0 else min(limit, MAX_RESULT_LIMIT)
    offset = max(0, offset)
    meta = load_user_directory_scan_meta()
    if not meta:
        return {
            "ok": True,
            "meta": None,
            "summary": [],
            "items": [],
            "item_count": 0,
            "large_files": [],
            "stats": None,
            "scan_config": None,
        }

    scan_id = meta["scan_id"]
    items = load_user_directory_items(
        scan_id=scan_id,
        category=category,
        item_type=item_type,
        search=search,
        min_size=min_size,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
    )
    summary = load_user_directory_summary(scan_id)
    large_files = load_user_directory_large_files(scan_id, limit=20)

    return _augment_payload(meta, summary, {
        "ok": True,
        "meta": meta,
        "summary": summary,
        "items": items,
        "item_count": count_user_directory_items(
            scan_id=scan_id,
            category=category,
            item_type=item_type,
            search=search,
            min_size=min_size,
        ),
        "large_files": large_files,
    })


def get_user_directory_top_items(limit: int = TOP_ITEMS_LIMIT) -> dict:
    limit = TOP_ITEMS_LIMIT if limit <= 0 else min(limit, TOP_ITEMS_LIMIT)
    meta = load_user_directory_scan_meta()
    if not meta:
        return {"ok": True, "meta": None, "items": [], "item_count": 0}

    scan_id = meta["scan_id"]
    items = load_user_directory_top_items(scan_id=scan_id, limit=limit)
    return {
        "ok": True,
        "meta": meta,
        "items": items,
        "item_count": len(items),
    }


def clear_user_directory_results() -> dict:
    clear_user_directory_scan()
    return {"ok": True}
