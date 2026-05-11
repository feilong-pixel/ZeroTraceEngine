from core.registry_models import RegistryIssueItem
from core.services import registry_cleanup_service as service
from core.services.registry_cleanup_service import (
    execute_registry_plan,
    generate_registry_plan,
    get_registry_plan_detail,
    get_registry_restore_preview,
)
from core.storage.database import init_db
from core.storage.clean_log_repository import list_clean_records
from core.storage.registry_cleanup_repository import list_plans
from core.storage.registry_scan_repository import save_registry_scan_results


def test_review_registry_plan_can_be_saved_but_not_executed(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setattr(service, "REGISTRY_RECYCLE_ROOT", tmp_path / "registry-backups")
    init_db()
    item = RegistryIssueItem(
        id="review-1",
        category="OrphanCOM",
        risk="Medium",
        source="COM",
        hive="HKCU",
        key_path=r"Software\Classes\CLSID\{demo}\InprocServer32",
        value_name="",
        value_data=r"C:\missing\demo.dll",
        target_path=r"C:\missing\demo.dll",
        description="COM component references missing DLL",
        rule_id="com_missing_dll",
        confidence="Low",
        validation_status="path_missing",
        skip_reason="low_confidence",
        selected=False,
    )
    save_registry_scan_results([item])

    plan = generate_registry_plan([item.id])
    result = execute_registry_plan(plan["plan_id"])

    assert plan["review_action_count"] == 1
    assert plan["can_execute"] is False
    assert result["ok"] is False
    assert result["requires_review"] is True
    assert result["missing_review_action_ids"]


def test_review_registry_plan_executes_after_manual_confirmation(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setattr(service, "REGISTRY_RECYCLE_ROOT", tmp_path / "registry-backups")
    init_db()
    item = RegistryIssueItem(
        id="review-confirmed",
        category="OrphanCOM",
        risk="Medium",
        source="COM",
        hive="HKCU",
        key_path=r"Software\Classes\CLSID\{demo}\InprocServer32",
        value_name="",
        value_data=r"C:\missing\demo.dll",
        target_path=r"C:\missing\demo.dll",
        description="COM component references missing DLL",
        rule_id="com_missing_dll",
        confidence="Low",
        validation_status="path_missing",
        skip_reason="low_confidence",
        selected=False,
    )
    save_registry_scan_results([item])
    plan = generate_registry_plan([item.id])
    review_action_id = plan["review_actions"][0]["id"]
    monkeypatch.setattr(service, "_snapshot_mismatches", lambda _plan: [])
    monkeypatch.setattr(service, "_delete_registry_value", lambda *_args: None)

    result = execute_registry_plan(
        plan["plan_id"],
        confirmed_review_action_ids=[review_action_id],
    )

    assert result["ok"] is True
    assert result["succeeded"] == 1


def test_diagnostic_only_registry_plan_cannot_execute_even_when_confirmed(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setattr(service, "REGISTRY_RECYCLE_ROOT", tmp_path / "registry-backups")
    init_db()
    item = RegistryIssueItem(
        id="diag-1",
        category="StartupIssue",
        risk="Safe",
        source="ScheduledTask",
        hive="HKCC",
        key_path=r"C:\Windows\System32\Tasks\Demo",
        value_name="Command",
        value_data=r"C:\missing\task.exe",
        target_path=r"C:\missing\task.exe",
        description="Scheduled task references missing executable",
        rule_id="scheduled_task_missing_exe",
        confidence="Low",
        validation_status="path_missing",
        skip_reason="diagnostic_only",
        selected=False,
    )
    save_registry_scan_results([item])
    plan = generate_registry_plan([item.id])
    action_id = plan["review_actions"][0]["id"]

    result = execute_registry_plan(
        plan["plan_id"],
        confirmed_review_action_ids=[action_id],
    )

    assert result["ok"] is False
    assert result["diagnostic_only"] is True


def test_registry_plan_history_includes_action_count(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setattr(service, "REGISTRY_RECYCLE_ROOT", tmp_path / "registry-backups")
    init_db()
    item = RegistryIssueItem(
        id="startup-1",
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
    save_registry_scan_results([item])

    plan = generate_registry_plan([item.id])
    plans = list_plans()

    assert plans[0]["plan_id"] == plan["plan_id"]
    assert plans[0]["action_count"] == 1
    assert plans[0]["status"] == "pending"


def test_registry_plan_detail_includes_action_metadata(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setattr(service, "REGISTRY_RECYCLE_ROOT", tmp_path / "registry-backups")
    init_db()
    item = RegistryIssueItem(
        id="startup-detail",
        category="StartupIssue",
        risk="Safe",
        source="Startup",
        hive="HKCU",
        key_path=r"Software\Microsoft\Windows\CurrentVersion\Run",
        value_name="DemoDetail",
        value_data=r"C:\missing\demo.exe",
        target_path=r"C:\missing\demo.exe",
        description="Startup item points to missing file",
        rule_id="startup_missing_target",
        confidence="High",
        validation_status="path_missing",
        selected=True,
    )
    save_registry_scan_results([item])

    plan = generate_registry_plan([item.id])
    detail = get_registry_plan_detail(plan["plan_id"])
    action = detail["plan"]["actions"][0]

    assert detail["plan"]["plan_id"] == plan["plan_id"]
    assert detail["plan"]["action_count"] == 1
    assert action["value_name"] == "DemoDetail"
    assert action["confidence"] == "High"
    assert action["validation_status"] == "path_missing"
    assert action["backup_path"].endswith(action["reg_file"])


def test_registry_execute_blocks_when_snapshot_changed(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setattr(service, "REGISTRY_RECYCLE_ROOT", tmp_path / "registry-backups")
    init_db()
    item = RegistryIssueItem(
        id="startup-snapshot",
        category="StartupIssue",
        risk="Safe",
        source="Startup",
        hive="HKCU",
        key_path=r"Software\Microsoft\Windows\CurrentVersion\Run",
        value_name="DemoSnapshot",
        value_data=r"C:\missing\demo.exe",
        target_path=r"C:\missing\demo.exe",
        description="Startup item points to missing file",
        rule_id="startup_missing_target",
        confidence="High",
        validation_status="path_missing",
        selected=True,
    )
    save_registry_scan_results([item])
    plan = generate_registry_plan([item.id])
    monkeypatch.setattr(service, "_snapshot_mismatches", lambda _plan: ["snapshot changed"])
    monkeypatch.setattr(service, "_delete_registry_value", lambda *_args: None)

    result = execute_registry_plan(plan["plan_id"])

    assert result["ok"] is False
    assert result["snapshot_changed"] is True
    assert result["failed"] == 1


def test_registry_execute_writes_unified_audit_log(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setattr(service, "REGISTRY_RECYCLE_ROOT", tmp_path / "registry-backups")
    init_db()
    item = RegistryIssueItem(
        id="startup-audit",
        category="StartupIssue",
        risk="Safe",
        source="Startup",
        hive="HKCU",
        key_path=r"Software\Microsoft\Windows\CurrentVersion\Run",
        value_name="DemoAudit",
        value_data=r"C:\missing\demo.exe",
        target_path=r"C:\missing\demo.exe",
        description="Startup item points to missing file",
        rule_id="startup_missing_target",
        confidence="High",
        validation_status="path_missing",
        selected=True,
    )
    save_registry_scan_results([item])
    plan = generate_registry_plan([item.id])
    monkeypatch.setattr(service, "_snapshot_mismatches", lambda _plan: [])
    monkeypatch.setattr(service, "_delete_registry_value", lambda *_args: None)

    result = execute_registry_plan(plan["plan_id"])
    records = list_clean_records(active_only=False)

    assert result["ok"] is True
    assert records[0]["action"] == "registry_execute"
    assert records[0]["file_type"] == "registry"
    assert records[0]["source"] == "registry"
    assert records[0]["hash"] == plan["plan_id"]


def test_restore_requires_confirmation_when_current_registry_differs(tmp_path, monkeypatch, isolated_db):
    monkeypatch.setattr(service, "REGISTRY_RECYCLE_ROOT", tmp_path / "registry-backups")
    init_db()
    item = RegistryIssueItem(
        id="restore-preview",
        category="StartupIssue",
        risk="Safe",
        source="Startup",
        hive="HKCU",
        key_path=r"Software\Microsoft\Windows\CurrentVersion\Run",
        value_name="DemoRestore",
        value_data=r"C:\missing\demo.exe",
        target_path=r"C:\missing\demo.exe",
        description="Startup item points to missing file",
        rule_id="startup_missing_target",
        confidence="High",
        validation_status="path_missing",
        selected=True,
    )
    save_registry_scan_results([item])
    plan = generate_registry_plan([item.id])
    monkeypatch.setattr(service, "_export_to_reg_content", lambda _action: "changed")

    preview = get_registry_restore_preview(plan["plan_id"])
    result = service.restore_registry_plan(plan["plan_id"])

    assert preview["requires_confirmation"] is True
    assert preview["overwrite_count"] == 1
    assert result["ok"] is False
    assert result["requires_restore_confirmation"] is True
