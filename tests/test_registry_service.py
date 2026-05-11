from core.registry_models import RegistryIssueItem, RegistryScannerReport
from core.services import registry_service
from core.storage.database import init_db
from core.storage.registry_scan_repository import (
    load_registry_scan_reports,
    load_registry_scan_results,
    save_registry_scan_results,
)


def make_registry_issue(issue_id: str = "startup-1") -> RegistryIssueItem:
    return RegistryIssueItem(
        id=issue_id,
        category="StartupIssue",
        risk="Safe",
        source="Startup",
        hive="HKCU",
        key_path=r"Software\Microsoft\Windows\CurrentVersion\Run",
        value_name="Demo",
        value_data=r"C:\missing\demo.exe",
        target_path=r"C:\missing\demo.exe",
        description="Startup item points to missing file",
        rule_id="startup_missing_target",
        confidence="High",
        validation_status="path_missing",
        selected=True,
    )


def make_registry_report() -> RegistryScannerReport:
    return RegistryScannerReport(
        hive="HKCU",
        key_path=r"Software\Microsoft\Windows\CurrentVersion\Run",
        scan_type="startup",
        status="ok",
        checked=1,
        issues=1,
    )


def test_execute_registry_scan_saves_and_returns_structured_results(isolated_db, monkeypatch):
    init_db()
    issue = make_registry_issue()
    report = make_registry_report()

    monkeypatch.setattr(
        registry_service,
        "scan_registry",
        lambda scope, mode: {
            "issues": [issue],
            "stats": {"unused": True},
            "reports": [report],
        },
    )

    result = registry_service.execute_registry_scan(scope="Standard", mode="Safe")

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["issues"][0]["id"] == "startup-1"
    assert result["stats"]["by_risk"]["Safe"] == 1
    assert result["reports"][0]["scan_type"] == "startup"
    assert [item.id for item in load_registry_scan_results()] == ["startup-1"]
    assert [item.scan_type for item in load_registry_scan_reports()] == ["startup"]


def test_get_saved_registry_results_rebuilds_stats_from_storage(isolated_db):
    init_db()
    save_registry_scan_results([make_registry_issue()], [make_registry_report()])

    result = registry_service.get_saved_registry_results()

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["stats"]["by_category"]["StartupIssue"] == 1
    assert result["reports"][0]["checked"] == 1


def test_clear_saved_registry_results_returns_explicit_result(isolated_db):
    init_db()
    save_registry_scan_results([make_registry_issue()], [make_registry_report()])

    result = registry_service.clear_saved_registry_results()

    assert result == {
        "ok": True,
        "cleared": "registry_scan_results",
    }
    assert load_registry_scan_results() == []
    assert load_registry_scan_reports() == []
