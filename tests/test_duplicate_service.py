from pathlib import Path

from core.services.duplicate_service import (
    QUICK_HASH_BYTES,
    compute_quick_hash,
    create_duplicate_cleanup_plan,
    scan_duplicates,
)
from core.storage import database
from core.storage.scan_results_repository import list_scan_results


def test_duplicate_scan_groups_equal_files(repo_tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", repo_tmp_path)
    monkeypatch.setattr(database, "DB_PATH", repo_tmp_path / "zerotrace.db")

    scan_root = repo_tmp_path / "photos"
    scan_root.mkdir()
    (scan_root / "a.jpg").write_bytes(b"same image bytes")
    (scan_root / "b.jpg").write_bytes(b"same image bytes")
    (scan_root / "c.jpg").write_bytes(b"different")

    result = scan_duplicates([str(scan_root)])

    assert result["group_count"] == 1
    assert result["duplicate_file_count"] == 2
    assert result["groups"][0]["reclaimable_size"] == len(b"same image bytes")
    assert result["groups"][0]["display_name"] in {"a.jpg", "b.jpg"}
    assert result["groups"][0]["recommended_keep_path"]
    assert result["groups"][0]["risk_counts"]["medium"] == 2
    assert {item["category"] for item in result["groups"][0]["files"]} == {"image"}


def test_duplicate_plan_writes_scan_results(repo_tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", repo_tmp_path)
    monkeypatch.setattr(database, "DB_PATH", repo_tmp_path / "zerotrace.db")

    duplicate_path = repo_tmp_path / "duplicate.txt"
    duplicate_path.write_text("same", encoding="utf-8")

    result = create_duplicate_cleanup_plan([str(duplicate_path)])
    rows = list_scan_results()

    assert result["ok"] is True
    assert result["count"] == 1
    assert rows[0]["path"] == str(duplicate_path.resolve())
    assert rows[0]["category"] == "duplicate"
    assert rows[0]["scanner"] == "DuplicateScanner"


def test_duplicate_quick_hash_uses_middle_and_tail_segments(repo_tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", repo_tmp_path)
    monkeypatch.setattr(database, "DB_PATH", repo_tmp_path / "zerotrace.db")

    scan_root = repo_tmp_path / "videos"
    scan_root.mkdir()
    head = b"h" * QUICK_HASH_BYTES
    tail = b"t" * QUICK_HASH_BYTES
    (scan_root / "left.mp4").write_bytes(head + (b"a" * QUICK_HASH_BYTES) + tail)
    (scan_root / "right.mp4").write_bytes(head + (b"b" * QUICK_HASH_BYTES) + tail)

    assert compute_quick_hash(scan_root / "left.mp4", (scan_root / "left.mp4").stat().st_size) != compute_quick_hash(scan_root / "right.mp4", (scan_root / "right.mp4").stat().st_size)

    result = scan_duplicates([str(scan_root)])

    assert result["candidate_files"] == 2
    assert result["group_count"] == 0
