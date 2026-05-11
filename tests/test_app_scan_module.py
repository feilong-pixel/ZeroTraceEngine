from datetime import datetime, timezone
from pathlib import Path

from core.app_scan_models import AppScanItem
from core.scanners import app_scanner
from core.services import app_scan_service
from core.storage import app_scan_repository
from core.storage.database import init_db


def make_app(
    app_id: str,
    name: str,
    path: str | None,
    size: int | None = None,
    notes: list[str] | None = None,
    is_valid: bool = True,
) -> AppScanItem:
    return AppScanItem(
        id=app_id,
        name=name,
        install_path=path,
        size_bytes=size,
        source="registry",
        is_valid=is_valid,
        notes=notes or ["From registry"],
    )


def test_registry_path_fallbacks_from_display_icon_and_uninstall_string(repo_tmp_path):
    icon_dir = repo_tmp_path / "IconApp"
    icon_dir.mkdir()
    icon_exe = icon_dir / "app.exe"
    icon_exe.write_text("exe", encoding="utf-8")

    uninstall_dir = repo_tmp_path / "UninstallApp"
    uninstall_dir.mkdir()
    uninstall_exe = uninstall_dir / "uninstall.exe"
    uninstall_exe.write_text("exe", encoding="utf-8")

    path, source = app_scanner._infer_install_path(None, f'"{icon_exe}",0', None)
    assert Path(path) == icon_dir
    assert source == "DisplayIcon"

    path, source = app_scanner._infer_install_path(None, None, f'"{uninstall_exe}" /S')
    assert Path(path) == uninstall_dir
    assert source == "UninstallString"


def test_registry_only_unknown_path_is_not_residual():
    app = make_app(
        "registry-only",
        "Registry Only App",
        None,
        notes=["From registry", "No install path (registry-only)"],
    )

    summary = app_scanner.build_summary([app], scanned_registry_keys=1, scanned_directories=0)

    assert app.is_valid is True
    assert summary.total_apps == 1
    assert summary.invalid_count == 0


def test_two_stage_scan_saves_discovery_before_size_update(isolated_db, monkeypatch):
    init_db()
    started_dt = datetime.now(timezone.utc)
    discovery = app_scanner.AppScanDiscovery(
        apps=[
            make_app("alpha", "Alpha", "C:/Apps/Alpha"),
            make_app("beta", "Beta", "C:/Apps/Beta", size=200, notes=["From registry", "Estimated size from registry"]),
        ],
        started_at="2026-05-11 10:00:00",
        started_at_dt=started_dt,
        scanned_registry_keys=3,
        scanned_directories=2,
    )

    monkeypatch.setattr(app_scan_service, "discover_app_scan", lambda progress_callback=None: discovery)

    def fake_complete_app_scan(discovery, max_concurrency, size_scan_timeout_seconds, progress_callback):
        meta = app_scan_repository.load_app_scan_meta()
        rows = app_scan_repository.load_app_items(meta["scan_id"], limit=100)
        assert len(rows) == 2
        assert {row["name"] for row in rows} == {"Alpha", "Beta"}
        assert next(row for row in rows if row["name"] == "Alpha")["size_bytes"] is None

        discovery.apps[0].size_bytes = 100
        discovery.apps[0].notes.append("Size computed from directory")
        summary = app_scanner.build_summary(discovery.apps, 3, 2)
        return app_scanner.AppScanResult(
            apps=discovery.apps,
            summary=summary,
            started_at=discovery.started_at,
            finished_at="2026-05-11 10:00:03",
            duration_ms=3000,
        )

    monkeypatch.setattr(app_scan_service, "complete_app_scan", fake_complete_app_scan)

    result = app_scan_service._run_app_scan_task("task-two-stage", 6, 8, lambda *_args: None)
    rows = app_scan_repository.load_app_items(result["scan_id"], limit=100)

    assert result["summary"]["total_apps"] == 2
    assert result["summary"]["total_size_bytes"] == 300
    assert {row["name"]: row["size_bytes"] for row in rows} == {"Alpha": 100, "Beta": 200}


def test_timed_out_count_and_size_rescan_update_summary_and_top_items(isolated_db, monkeypatch):
    init_db()
    apps = [
        make_app(
            "timeout",
            "Timed Out App",
            "C:/Apps/TimedOut",
            size=50,
            notes=[
                "From registry",
                "Partial size from directory",
                "Directory size scan timed out; partial size",
            ],
        ),
        make_app(
            "normal",
            "Normal App",
            "C:/Apps/Normal",
            size=80,
            notes=["From registry", "Estimated size from registry"],
        ),
    ]
    summary = app_scanner.build_summary(apps, scanned_registry_keys=2, scanned_directories=1)
    scan_id = app_scan_repository.save_app_scan(
        apps=apps,
        summary=summary,
        started_at="2026-05-11 10:00:00",
        finished_at="2026-05-11 10:00:01",
        duration_ms=1000,
    )

    assert app_scan_repository.count_app_timed_out_items(scan_id) == 1

    def fake_compute_sizes(targets, max_concurrency, size_scan_timeout_seconds):
        assert [target.name for target in targets] == ["Timed Out App"]
        assert size_scan_timeout_seconds is None
        targets[0].size_bytes = 120
        targets[0].notes.append("Size computed from directory")

    monkeypatch.setattr(app_scan_service, "compute_sizes", fake_compute_sizes)

    result = app_scan_service._run_size_rescan_task("task-size-rescan", 6)
    top_items = app_scan_service.get_app_scan_top_items(limit=16)["items"]

    assert result["timed_out_count"] == 0
    assert result["summary"]["total_size_bytes"] == 200
    assert top_items[0]["name"] == "Timed Out App"
    assert top_items[0]["size_bytes"] == 120


def test_drive_usage_groups_valid_sized_apps_by_drive(isolated_db):
    init_db()
    apps = [
        make_app("c-app", "C App", "C:/Apps/CApp", size=100),
        make_app("d-app", "D App", "D:/Tools/DApp", size=300),
        make_app("unknown", "Unknown", None, size=50),
        make_app("pending", "Pending", "C:/Apps/Pending", size=None),
        make_app("invalid", "Invalid", "E:/Missing", size=999, is_valid=False),
    ]
    summary = app_scanner.build_summary(apps, scanned_registry_keys=5, scanned_directories=1)
    scan_id = app_scan_repository.save_app_scan(
        apps=apps,
        summary=summary,
        started_at="2026-05-11 10:00:00",
        finished_at="2026-05-11 10:00:01",
        duration_ms=1000,
    )

    usage = app_scan_repository.load_app_drive_usage(scan_id)

    assert usage["total_size_bytes"] == 400
    assert [(row["drive"], row["size_bytes"]) for row in usage["drives"]] == [("D:", 300), ("C:", 100)]
    assert usage["uncounted_count"] == 2
