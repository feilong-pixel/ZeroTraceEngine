from core.storage.duplicate_results_repository import (
    clear_duplicate_results,
    list_duplicate_results,
    save_duplicate_results,
)


def test_duplicate_results_repository_roundtrip(isolated_db):
    save_duplicate_results([
        {
            "hash": "hash-a",
            "files": [
                {
                    "path": "C:/photos/a.jpg",
                    "size": 123,
                    "mtime": "2026-05-04T10:30:00",
                    "root": "C:/photos",
                    "category": "image",
                    "source": "photos",
                    "risk_level": "medium",
                    "risk_reasons": ["shallow_root"],
                    "quick_hash": "quick-a",
                    "full_hash": "hash-a",
                }
            ],
        }
    ])

    rows = list_duplicate_results()

    assert rows[0]["path"] == "C:/photos/a.jpg"
    assert rows[0]["group_hash"] == "hash-a"
    assert rows[0]["risk_reasons"] == ["shallow_root"]

    clear_duplicate_results()
    assert list_duplicate_results() == []


def test_duplicate_results_repository_ignores_empty_paths(isolated_db):
    save_duplicate_results([
        {
            "hash": "hash-a",
            "files": [
                {
                    "path": "",
                    "size": 123,
                    "mtime": "2026-05-04T10:30:00",
                    "root": "C:/photos",
                    "category": "image",
                    "source": "photos",
                    "risk_level": "medium",
                    "risk_reasons": [],
                    "quick_hash": "quick-a",
                    "full_hash": "hash-a",
                }
            ],
        }
    ])

    assert list_duplicate_results() == []
