import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.models import ScanItem
from core.storage.file_hash_repository import (
    FileHashRecord,
    get_file_hash,
    mark_missing_hashes,
    upsert_file_hash,
)
from core.storage.scan_results_repository import clear_scan_results, save_scan_results

QUICK_HASH_BYTES = 4096
CHUNK_SIZE = 1024 * 1024
SUPPORTED_FILE_TYPES = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic"},
    "video": {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".m4v"},
    "document": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md"},
    "archive": {".zip", ".rar", ".7z", ".tar", ".gz"},
}


@dataclass(frozen=True)
class FileCandidate:
    path: Path
    root: Path
    size: int
    mtime: int


def scan_duplicates(raw_roots: list[str]) -> dict[str, Any]:
    roots = validate_roots(raw_roots)
    candidates = list(iter_files(roots))
    scanned_paths = {str(candidate.path) for candidate in candidates}

    by_size: dict[int, list[FileCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.size > 0:
            by_size[candidate.size].append(candidate)

    size_candidates = [
        candidate
        for group in by_size.values()
        if len(group) > 1
        for candidate in group
    ]

    records_by_quick: dict[tuple[int, str], list[tuple[FileCandidate, FileHashRecord]]] = defaultdict(list)
    for candidate in size_candidates:
        record = get_or_compute_hash(candidate)
        records_by_quick[(candidate.size, record.quick_hash)].append((candidate, record))

    records_by_full: dict[tuple[int, str], list[tuple[FileCandidate, FileHashRecord]]] = defaultdict(list)
    for group in records_by_quick.values():
        if len(group) <= 1:
            continue
        for candidate, record in group:
            records_by_full[(candidate.size, record.full_hash)].append((candidate, record))

    groups = []
    duplicate_file_count = 0
    reclaimable_size = 0
    for index, ((size, full_hash), group) in enumerate(records_by_full.items(), start=1):
        if len(group) <= 1:
            continue

        files = [build_file_payload(candidate, record) for candidate, record in group]
        files.sort(key=lambda item: (item["mtime"] or 0, item["path"]))
        group_reclaimable = size * (len(files) - 1)
        recommended_file = recommend_keep_file(files)
        duplicate_file_count += len(files)
        reclaimable_size += group_reclaimable
        groups.append({
            "id": f"group-{index}",
            "hash": full_hash,
            "size": size,
            "file_count": len(files),
            "reclaimable_size": group_reclaimable,
            "display_name": Path(files[0]["path"]).name,
            "recommended_keep_path": recommended_file["path"],
            "recommended_keep_reason": recommended_file["keep_reason"],
            "risk_counts": count_risks(files),
            "files": files,
        })

    groups.sort(key=lambda group: group["reclaimable_size"], reverse=True)
    missing_hashes = mark_missing_hashes(scanned_paths, [str(root) for root in roots])

    return {
        "ok": True,
        "roots": [str(root) for root in roots],
        "scanned_files": len(candidates),
        "candidate_files": len(size_candidates),
        "group_count": len(groups),
        "duplicate_file_count": duplicate_file_count,
        "reclaimable_size": reclaimable_size,
        "missing_hashes": missing_hashes,
        "groups": groups,
    }


def create_duplicate_cleanup_plan(paths: list[str]) -> dict[str, Any]:
    unique_paths = list(dict.fromkeys(str(path).strip() for path in paths if str(path).strip()))
    items: list[ScanItem] = []

    for raw_path in unique_paths:
        path = Path(raw_path).expanduser().resolve(strict=True)
        if not path.is_file():
            continue
        stat = path.stat()
        record = get_or_compute_hash(
            FileCandidate(path=path, root=path.parent, size=stat.st_size, mtime=int(stat.st_mtime))
        )
        risk_level, _risk_reasons = classify_risk(path, path.parent)
        items.append(
            ScanItem(
                path=str(path),
                size=stat.st_size,
                mtime=datetime.fromtimestamp(stat.st_mtime),
                file_type="duplicate",
                category="duplicate",
                source=path.parent.name or "Duplicate Scan",
                scanner="DuplicateScanner",
                risk_level=risk_level,
                hash=record.full_hash,
            )
        )

    clear_scan_results()
    save_scan_results(items)

    return {
        "ok": True,
        "count": len(items),
        "paths": [item.path for item in items],
    }


def validate_roots(raw_roots: list[str]) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()

    for raw_root in raw_roots:
        text = str(raw_root).strip().strip('"')
        if not text:
            continue
        root = Path(text).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"Scan root is not a folder: {text}")
        root_text = str(root)
        if root_text not in seen:
            seen.add(root_text)
            roots.append(root)

    if not roots:
        raise ValueError("At least one existing folder is required.")

    return roots


def iter_files(roots: list[Path]):
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                dirname for dirname in dirnames
                if not should_skip_path(Path(dirpath) / dirname)
            ]
            for filename in filenames:
                path = Path(dirpath) / filename
                if should_skip_path(path):
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if not path.is_file():
                    continue
                yield FileCandidate(path=path.resolve(), root=root, size=stat.st_size, mtime=int(stat.st_mtime))


def should_skip_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return any(part in parts for part in {"zerotracerecycle", ".git", "__pycache__"})


def get_or_compute_hash(candidate: FileCandidate) -> FileHashRecord:
    path_text = str(candidate.path)
    cached = get_file_hash(path_text)
    if cached and cached.size == candidate.size and cached.mtime == candidate.mtime:
        return cached

    quick_hash = compute_quick_hash(candidate.path, candidate.size)
    full_hash = compute_hash(candidate.path)
    return upsert_file_hash(
        path=path_text,
        size=candidate.size,
        mtime=candidate.mtime,
        quick_hash=quick_hash,
        full_hash=full_hash,
    )


def compute_hash(path: Path, limit: int | None = None) -> str:
    hasher = hashlib.sha1()
    remaining = limit

    with path.open("rb") as handle:
        while True:
            read_size = CHUNK_SIZE if remaining is None else min(CHUNK_SIZE, remaining)
            if read_size <= 0:
                break
            chunk = handle.read(read_size)
            if not chunk:
                break
            hasher.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)

    return hasher.hexdigest()


def compute_quick_hash(path: Path, size: int) -> str:
    hasher = hashlib.sha1()
    offsets = quick_hash_offsets(size)

    with path.open("rb") as handle:
        for offset in offsets:
            handle.seek(offset)
            hasher.update(handle.read(QUICK_HASH_BYTES))

    return hasher.hexdigest()


def quick_hash_offsets(size: int) -> list[int]:
    if size <= QUICK_HASH_BYTES:
        return [0]
    if size <= QUICK_HASH_BYTES * 2:
        return [0]
    middle = max((size // 2) - (QUICK_HASH_BYTES // 2), 0)
    tail = max(size - QUICK_HASH_BYTES, 0)
    return list(dict.fromkeys([0, middle, tail]))


def build_file_payload(candidate: FileCandidate, record: FileHashRecord) -> dict[str, Any]:
    path = candidate.path
    risk_level, risk_reasons = classify_risk(path, candidate.root)
    return {
        "path": str(path),
        "size": candidate.size,
        "mtime": datetime.fromtimestamp(candidate.mtime).isoformat(),
        "source": candidate.root.name or str(candidate.root),
        "root": str(candidate.root),
        "category": classify_category(path),
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
        "quick_hash": record.quick_hash,
        "full_hash": record.full_hash,
    }


def classify_category(path: Path) -> str:
    suffix = path.suffix.lower()
    for category, suffixes in SUPPORTED_FILE_TYPES.items():
        if suffix in suffixes:
            return category
    return "other"


def classify_risk(path: Path, root: Path) -> tuple[str, list[str]]:
    reasons: list[str] = []
    try:
        relative_depth = len(path.relative_to(root).parts)
    except ValueError:
        relative_depth = len(path.parts)

    lowered_parts = {part.lower() for part in path.parts}
    high_markers = {"desktop", "documents", "workspace", "work", "source", "src"}
    if lowered_parts & high_markers:
        reasons.append("protected_location")
    if ".git" in lowered_parts:
        reasons.append("git_repository")

    if reasons:
        return "high", reasons
    if relative_depth <= 2:
        return "medium", ["shallow_root"]
    return "low", ["nested_file"]


def count_risks(files: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"low": 0, "medium": 0, "high": 0}
    for file in files:
        risk = file.get("risk_level") or "low"
        counts[risk] = counts.get(risk, 0) + 1
    return counts


def recommend_keep_file(files: list[dict[str, Any]]) -> dict[str, Any]:
    risk_weight = {"low": 0, "medium": 1, "high": 2}

    def score(file: dict[str, Any]) -> tuple[int, float, int, str]:
        mtime = datetime.fromisoformat(file["mtime"]).timestamp() if file.get("mtime") else 0
        depth = len(Path(file["path"]).parts)
        return (
            -risk_weight.get(file.get("risk_level") or "low", 1),
            mtime,
            -depth,
            file["path"],
        )

    selected = max(files, key=score)
    reasons = ["latest_modified"]
    if selected.get("risk_level") == "low":
        reasons.append("lower_risk")
    if len(Path(selected["path"]).parts) > 3:
        reasons.append("stable_nested_path")
    return {**selected, "keep_reason": reasons}
