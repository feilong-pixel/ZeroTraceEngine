from pathlib import Path

from core.services.duplicate_service import (
    QUICK_HASH_BYTES,
    compute_quick_hash,
    create_duplicate_cleanup_plan,
    load_saved_duplicate_scan_results,
    scan_duplicates,
)
from core.storage import database
from core.storage.duplicate_results_repository import list_duplicate_results, save_duplicate_results
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


def test_duplicate_scan_persists_unfinished_results(repo_tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", repo_tmp_path)
    monkeypatch.setattr(database, "DB_PATH", repo_tmp_path / "zerotrace.db")

    scan_root = repo_tmp_path / "photos"
    scan_root.mkdir()
    (scan_root / "a.jpg").write_bytes(b"same")
    (scan_root / "b.jpg").write_bytes(b"same")

    result = scan_duplicates([str(scan_root)])
    rows = list_duplicate_results()
    saved = load_saved_duplicate_scan_results()

    assert result["ok"] is True
    assert result["group_count"] == 1
    assert {row["path"] for row in rows} == {
        str((scan_root / "a.jpg").resolve()),
        str((scan_root / "b.jpg").resolve()),
    }
    assert {row["category"] for row in rows} == {"image"}
    assert list_scan_results() == []
    assert saved["group_count"] == 1
    assert saved["duplicate_file_count"] == 2


def test_duplicate_plan_writes_selected_paths_to_scan_results(repo_tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", repo_tmp_path)
    monkeypatch.setattr(database, "DB_PATH", repo_tmp_path / "zerotrace.db")

    scan_root = repo_tmp_path / "photos"
    scan_root.mkdir()
    keep_path = scan_root / "a.jpg"
    duplicate_path = scan_root / "b.jpg"
    keep_path.write_bytes(b"same")
    duplicate_path.write_bytes(b"same")

    scan_duplicates([str(scan_root)])
    result = create_duplicate_cleanup_plan([str(duplicate_path)])
    rows = list_scan_results()
    duplicate_rows = list_duplicate_results()

    assert result["ok"] is True
    assert result["paths"] == [str(duplicate_path.resolve())]
    assert [row["path"] for row in rows] == [str(duplicate_path.resolve())]
    assert rows[0]["category"] == "duplicate"
    assert rows[0]["scanner"] == "DuplicateScanner"
    assert {row["path"] for row in duplicate_rows} == {str(keep_path.resolve()), str(duplicate_path.resolve())}


def test_saved_duplicate_results_ignore_missing_paths(repo_tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", repo_tmp_path)
    monkeypatch.setattr(database, "DB_PATH", repo_tmp_path / "zerotrace.db")

    scan_root = repo_tmp_path / "photos"
    scan_root.mkdir()
    existing_a = scan_root / "a.jpg"
    existing_b = scan_root / "b.jpg"
    missing = scan_root / "missing.jpg"
    existing_a.write_bytes(b"same")
    existing_b.write_bytes(b"same")

    save_duplicate_results([
        {
            "hash": "same-hash",
            "files": [
                {
                    "path": str(existing_a),
                    "size": 4,
                    "mtime": "2026-05-04T10:30:00",
                    "root": str(scan_root),
                    "category": "image",
                    "source": "photos",
                    "risk_level": "low",
                    "risk_reasons": [],
                    "quick_hash": "quick",
                    "full_hash": "same-hash",
                },
                {
                    "path": str(existing_b),
                    "size": 4,
                    "mtime": "2026-05-04T10:31:00",
                    "root": str(scan_root),
                    "category": "image",
                    "source": "photos",
                    "risk_level": "low",
                    "risk_reasons": [],
                    "quick_hash": "quick",
                    "full_hash": "same-hash",
                },
                {
                    "path": str(missing),
                    "size": 4,
                    "mtime": "2026-05-04T10:32:00",
                    "root": str(scan_root),
                    "category": "image",
                    "source": "photos",
                    "risk_level": "low",
                    "risk_reasons": [],
                    "quick_hash": "quick",
                    "full_hash": "same-hash",
                },
            ],
        }
    ])

    saved = load_saved_duplicate_scan_results()

    assert saved["group_count"] == 1
    assert saved["duplicate_file_count"] == 2
    assert {file["path"] for file in saved["groups"][0]["files"]} == {
        str(existing_a.resolve()),
        str(existing_b.resolve()),
    }


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
