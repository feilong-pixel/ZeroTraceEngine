"""
AppScanService — orchestrates scan execution and result retrieval.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Optional
from uuid import uuid4

from core.app_scan_models import AppScanItem
from core.scanners.app_scanner import build_summary, complete_app_scan, compute_sizes, discover_app_scan, run_app_scan
from core.storage.app_scan_repository import (
    clear_app_scan,
    count_app_items,
    count_app_timed_out_items,
    load_app_drive_usage,
    load_app_items,
    load_app_scan_meta,
    load_app_scan_summary,
    load_app_top_items,
    save_app_scan,
    update_app_scan,
)

MAX_RESULT_LIMIT = 500
DEFAULT_RESULT_LIMIT = 100
TOP_ITEMS_LIMIT = 16
MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 16
MIN_SIZE_SCAN_TIMEOUT_SECONDS = 2
MAX_SIZE_SCAN_TIMEOUT_SECONDS = 60
DEFAULT_SIZE_SCAN_TIMEOUT_SECONDS = 8


@dataclass
class AppScanTask:
    task_id: str
    started_at: str
    future: Future | None = None
    status: str = "running"
    stage: str = "queued"
    progress: dict = field(default_factory=dict)
    result: dict | None = None
    error: str | None = None


_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="app-scan")
_TASKS: dict[str, AppScanTask] = {}
_TASK_LOCK = Lock()


def clamp_concurrency(value: int) -> int:
    return max(MIN_CONCURRENCY, min(value, MAX_CONCURRENCY))


def clamp_size_scan_timeout(value: int) -> int:
    return max(MIN_SIZE_SCAN_TIMEOUT_SECONDS, min(value, MAX_SIZE_SCAN_TIMEOUT_SECONDS))


def start_app_scan_task(max_concurrency: int = 6, size_scan_timeout_seconds: int = DEFAULT_SIZE_SCAN_TIMEOUT_SECONDS) -> dict:
    max_concurrency = clamp_concurrency(max_concurrency)
    size_scan_timeout_seconds = clamp_size_scan_timeout(size_scan_timeout_seconds)
    with _TASK_LOCK:
        for task in _TASKS.values():
            if task.status == "running" and (task.future is None or not task.future.done()):
                return {
                    "ok": True,
                    "task_id": task.task_id,
                    "status": task.status,
                    "stage": task.stage,
                    "progress": task.progress,
                    "started_at": task.started_at,
                    "reused": True,
                }

    task_id = str(uuid4())
    started_at = datetime.now(timezone.utc).isoformat()

    def update_progress(stage: str, payload: dict) -> None:
        with _TASK_LOCK:
            task = _TASKS.get(task_id)
            if task is None:
                return
            task.stage = stage
            task.progress = payload

    task = AppScanTask(task_id=task_id, started_at=started_at)
    with _TASK_LOCK:
        _TASKS[task_id] = task
    future = _EXECUTOR.submit(_run_app_scan_task, task_id, max_concurrency, size_scan_timeout_seconds, update_progress)
    with _TASK_LOCK:
        task.future = future
    return {"ok": True, "task_id": task_id, "status": task.status, "stage": task.stage, "progress": task.progress, "started_at": started_at}


def start_app_size_rescan_task(max_concurrency: int = 6) -> dict:
    max_concurrency = clamp_concurrency(max_concurrency)
    with _TASK_LOCK:
        for task in _TASKS.values():
            if task.status == "running" and (task.future is None or not task.future.done()):
                return {
                    "ok": True,
                    "task_id": task.task_id,
                    "status": task.status,
                    "stage": task.stage,
                    "progress": task.progress,
                    "started_at": task.started_at,
                    "reused": True,
                }

    task_id = str(uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    task = AppScanTask(task_id=task_id, started_at=started_at, stage="size_rescan")
    with _TASK_LOCK:
        _TASKS[task_id] = task
    future = _EXECUTOR.submit(_run_size_rescan_task, task_id, max_concurrency)
    with _TASK_LOCK:
        task.future = future
    return {"ok": True, "task_id": task_id, "status": task.status, "stage": task.stage, "progress": task.progress, "started_at": started_at}


def get_app_scan_task(task_id: str) -> dict:
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
    if task is None:
        return {"ok": False, "status": "missing", "error": "App scan task not found"}

    if task.future and task.future.done() and task.status == "running":
        try:
            task.result = task.future.result()
            task.status = "completed"
            task.stage = "completed"
        except Exception as exc:  # pragma: no cover - defensive task boundary
            task.error = str(exc)
            task.status = "error"
            task.stage = "error"
        _trim_finished_tasks()

    response = {
        "ok": task.status != "error",
        "task_id": task.task_id,
        "status": task.status,
        "stage": task.stage,
        "progress": task.progress,
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


def _run_app_scan_task(task_id: str, max_concurrency: int, size_scan_timeout_seconds: int, progress_callback) -> dict:
    discovery = discover_app_scan(progress_callback=progress_callback)
    initial_summary = build_summary(
        discovery.apps,
        discovery.scanned_registry_keys,
        discovery.scanned_directories,
    )
    now = datetime.now(timezone.utc)
    scan_id = save_app_scan(
        apps=discovery.apps,
        summary=initial_summary,
        started_at=discovery.started_at,
        finished_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        duration_ms=int((now - discovery.started_at_dt).total_seconds() * 1000),
    )
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task:
            task.result = _scan_result_payload(scan_id, initial_summary)

    result = complete_app_scan(
        discovery,
        max_concurrency=clamp_concurrency(max_concurrency),
        size_scan_timeout_seconds=clamp_size_scan_timeout(size_scan_timeout_seconds),
        progress_callback=progress_callback,
    )
    update_app_scan(
        scan_id=scan_id,
        apps=result.apps,
        summary=result.summary,
        finished_at=result.finished_at,
        duration_ms=result.duration_ms,
    )
    return _scan_result_payload(scan_id, result.summary)


def _scan_result_payload(scan_id: int, summary) -> dict:
    meta = load_app_scan_meta()
    return {
        "ok": True,
        "scan_id": scan_id,
        "meta": meta,
        "summary": summary.model_dump(),
        "items": load_app_items(scan_id, limit=DEFAULT_RESULT_LIMIT),
        "item_count": count_app_items(scan_id),
        "timed_out_count": count_app_timed_out_items(scan_id),
    }


def _is_timed_out_item(item: AppScanItem) -> bool:
    return (
        item.is_valid
        and bool(item.install_path)
        and (
            "Directory size scan timed out; partial size" in item.notes
            or "Directory size scan skipped after timeout" in item.notes
        )
    )


def _run_size_rescan_task(task_id: str, max_concurrency: int) -> dict:
    meta = load_app_scan_meta()
    if not meta:
        raise ValueError("No app scan results to update")

    scan_id = meta["scan_id"]
    rows = load_app_items(scan_id, limit=100000)
    apps = [AppScanItem(**row) for row in rows]
    targets = [app for app in apps if _is_timed_out_item(app)]
    with _TASK_LOCK:
        task = _TASKS.get(task_id)
        if task:
            task.stage = "size_rescan"
            task.progress = {"total_apps": len(targets), "size_scan_timeout_seconds": None}

    for app in targets:
        app.size_bytes = None
        app.notes = [
            note for note in app.notes
            if note not in {
                "Directory size scan timed out; partial size",
                "Directory size scan skipped after timeout",
                "Partial size from directory",
            }
        ]

    compute_sizes(
        targets,
        max_concurrency=clamp_concurrency(max_concurrency),
        size_scan_timeout_seconds=None,
    )
    app_by_id = {app.id: app for app in apps}
    for target in targets:
        app_by_id[target.id] = target
    updated_apps = list(app_by_id.values())
    summary = build_summary(
        updated_apps,
        meta.get("scanned_registry_keys", 0),
        meta.get("scanned_directories", 0),
    )
    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    update_app_scan(
        scan_id=scan_id,
        apps=updated_apps,
        summary=summary,
        finished_at=finished_at,
        duration_ms=meta.get("duration_ms", 0),
    )
    return _scan_result_payload(scan_id, summary)


def run_app_scan_service(
    max_concurrency: int = 6,
    size_scan_timeout_seconds: int = DEFAULT_SIZE_SCAN_TIMEOUT_SECONDS,
    progress_callback=None,
) -> dict:
    result = run_app_scan(
        max_concurrency=clamp_concurrency(max_concurrency),
        size_scan_timeout_seconds=clamp_size_scan_timeout(size_scan_timeout_seconds),
        progress_callback=progress_callback,
    )
    scan_id = save_app_scan(
        apps=result.apps,
        summary=result.summary,
        started_at=result.started_at,
        finished_at=result.finished_at,
        duration_ms=result.duration_ms,
    )

    meta = load_app_scan_meta()
    items = load_app_items(scan_id, limit=500)

    return {
        "ok": True,
        "scan_id": scan_id,
        "meta": meta,
        "summary": result.summary.model_dump(),
        "items": items,
        "item_count": count_app_items(scan_id),
        "timed_out_count": count_app_timed_out_items(scan_id),
    }


def get_app_scan_results(
    source: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    min_size: Optional[int] = None,
    order_by: str = "size_bytes",
    order_dir: str = "DESC",
    limit: int = 500,
    offset: int = 0,
) -> dict:
    limit = DEFAULT_RESULT_LIMIT if limit <= 0 else min(limit, MAX_RESULT_LIMIT)
    offset = max(0, offset)
    meta = load_app_scan_meta()
    if not meta:
        return {"ok": True, "meta": None, "summary": None, "items": [], "item_count": 0, "timed_out_count": 0}

    scan_id = meta["scan_id"]
    items = load_app_items(
        scan_id=scan_id,
        source=source,
        status=status,
        search=search,
        min_size=min_size,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
    )
    return {
        "ok": True,
        "meta": meta,
        "summary": load_app_scan_summary(scan_id),
        "items": items,
        "timed_out_count": count_app_timed_out_items(scan_id),
        "item_count": count_app_items(
            scan_id,
            source=source,
            status=status,
            search=search,
            min_size=min_size,
        ),
    }


def clear_app_scan_service() -> dict:
    clear_app_scan()
    return {"ok": True}


def get_app_scan_top_items(limit: int = TOP_ITEMS_LIMIT) -> dict:
    limit = TOP_ITEMS_LIMIT if limit <= 0 else min(limit, TOP_ITEMS_LIMIT)
    meta = load_app_scan_meta()
    if not meta:
        return {"ok": True, "meta": None, "items": [], "item_count": 0, "timed_out_count": 0}

    scan_id = meta["scan_id"]
    items = load_app_top_items(scan_id=scan_id, limit=limit)
    return {
        "ok": True,
        "meta": meta,
        "items": items,
        "item_count": len(items),
        "timed_out_count": count_app_timed_out_items(scan_id),
    }


def get_app_scan_drive_usage() -> dict:
    meta = load_app_scan_meta()
    if not meta:
        return {"ok": True, "meta": None, "total_size_bytes": 0, "drives": [], "uncounted_count": 0}

    usage = load_app_drive_usage(meta["scan_id"])
    return {
        "ok": True,
        "meta": meta,
        **usage,
        "timed_out_count": count_app_timed_out_items(meta["scan_id"]),
    }
