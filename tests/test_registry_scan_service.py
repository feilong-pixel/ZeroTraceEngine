from pathlib import Path

from core.registry_models import RegistryIssueItem
from core.services import registry_scan_service as service
from core.services.registry_scan_service import (
    _check_com_server,
    _check_app_path,
    _check_file_association,
    _check_scheduled_task_file,
    _check_com_treat_as,
    _confidence_for_issue,
    _default_selected_for_issue,
    _extract_exe,
    _extract_path_references,
    _file_exists,
    _make_issue,
    _validation_status,
    _build_stats,
)


class FakeKey:
    def __init__(self, path=""):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_extract_exe_keeps_quoted_target_without_args():
    assert _extract_exe(r'"C:\Program Files\App\app.exe" --flag') == r"C:\Program Files\App\app.exe"


def test_extract_path_references_handles_installshield_rundll32_command():
    refs = _extract_path_references(
        r'RunDll32 C:\PROGRA~2\COMMON~1\INSTAL~1\engine\6\INTEL3~1\Ctor.dll,LaunchSetup '
        r'"C:\Program Files (x86)\InstallShield Installation Information\{ID}\Setup.exe" -l0x9'
    )

    assert r"C:\PROGRA~2\COMMON~1\INSTAL~1\engine\6\INTEL3~1\Ctor.dll" in refs
    assert r"C:\Program Files (x86)\InstallShield Installation Information\{ID}\Setup.exe" in refs


def test_file_exists_resolves_bare_command(monkeypatch):
    monkeypatch.setattr(service.shutil, "which", lambda value: r"C:\Windows\System32\msiexec.exe" if value == "MsiExec.exe" else None)

    assert _file_exists("MsiExec.exe") is True
    assert _file_exists("MissingCommand.exe") is False


def test_validation_status_handles_missing_and_unverifiable_paths(monkeypatch, tmp_path):
    existing = tmp_path / "exists.exe"
    existing.write_text("x", encoding="utf-8")

    assert _validation_status(str(existing)) == "path_exists"
    assert _validation_status(str(tmp_path / "missing.exe")) == "path_missing"

    def raise_value_error(_path):
        raise ValueError("bad path")

    monkeypatch.setattr(Path, "exists", raise_value_error)
    assert _validation_status(r"C:\bad\path.exe") == "unverifiable_path"


def test_confidence_marks_uninstall_as_medium():
    assert _confidence_for_issue("InvalidUninstall", r"C:\missing\app.exe", "HKLM") == "Medium"
    assert _confidence_for_issue("InvalidUninstall", r"C:\missing\app.exe", "HKCU") == "Medium"


def test_confidence_marks_service_and_com_as_low():
    assert _confidence_for_issue("InvalidService", r"C:\missing\svc.exe", "HKLM") == "Low"
    assert _confidence_for_issue("OrphanCOM", r"C:\missing\demo.dll", "HKCR") == "Low"


def test_default_selection_only_allows_hkcu_startup_low_risk_high_confidence():
    assert _default_selected_for_issue("StartupIssue", "Safe", "High", "HKCU") is True
    assert _default_selected_for_issue("StartupIssue", "Safe", "High", "HKLM") is False
    assert _default_selected_for_issue("InvalidUninstall", "Safe", "High", "HKCU") is False


def test_make_issue_marks_uninstall_for_manual_review():
    item = _make_issue(
        id="u1",
        category="InvalidUninstall",
        risk="Safe",
        source="Uninstall",
        hive="HKCU",
        key_path=r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Demo",
        value_name=None,
        value_data=r"C:\missing\uninstall.exe",
        target_path=r"C:\missing\uninstall.exe",
        description="Demo uninstall target is missing",
        rule_id="uninstall_missing_target",
    )

    assert item.selected is False
    assert item.skip_reason == "manual_review_required"


def test_build_stats_includes_confidence_and_validation_status():
    item = RegistryIssueItem(
        id="1",
        category="StartupIssue",
        risk="Safe",
        source="Startup",
        hive="HKCU",
        key_path=r"Software\Microsoft\Windows\CurrentVersion\Run",
        value_name="Demo",
        value_data=r"C:\missing\demo.exe",
        target_path=r"C:\missing\demo.exe",
        description="Demo startup target is missing",
        rule_id="startup_missing_target",
        confidence="High",
        validation_status="path_missing",
    )

    stats = _build_stats([item])

    assert stats["by_confidence"]["High"] == 1
    assert stats["by_validation_status"]["path_missing"] == 1


def test_check_com_local_server_returns_review_only_missing_exe(monkeypatch):
    monkeypatch.setattr(service.winreg, "OpenKey", lambda *_args, **_kwargs: FakeKey())
    monkeypatch.setattr(
        service.winreg,
        "QueryValueEx",
        lambda _key, name: (r'"C:\Missing\Demo.exe" /Automation', service.winreg.REG_SZ),
    )
    monkeypatch.setattr(service, "_file_exists", lambda _path: False)

    item = _check_com_server(
        hive_short="HKCU",
        server_key_path=r"Software\Classes\CLSID\{demo}\LocalServer32",
        clsid="{demo}",
        mode="Advanced",
        server_kind="LocalServer32",
        rule_id="com_missing_local_server",
        target_label="local server executable",
    )

    assert item is not None
    assert item.rule_id == "com_missing_local_server"
    assert item.target_path == r"C:\Missing\Demo.exe"
    assert item.confidence == "Low"
    assert item.skip_reason == "low_confidence"
    assert item.selected is False


def test_check_com_treat_as_returns_review_only_missing_clsid(monkeypatch):
    def fake_open_key(_hive, path, **_kwargs):
        if path.endswith(r"TreatAs"):
            return FakeKey(path)
        raise OSError("missing target clsid")

    monkeypatch.setattr(service.winreg, "OpenKey", fake_open_key)
    monkeypatch.setattr(service.winreg, "QueryValueEx", lambda _key, _name: ("{target}", service.winreg.REG_SZ))

    item = _check_com_treat_as("HKCU", r"Software\Classes\CLSID", "{source}")

    assert item is not None
    assert item.rule_id == "com_treat_as_missing_clsid"
    assert item.confidence == "Low"
    assert item.skip_reason == "diagnostic_only"
    assert item.selected is False


def test_check_app_path_hkcu_missing_exe_is_explainable_candidate(monkeypatch):
    monkeypatch.setattr(service.winreg, "OpenKey", lambda _hive, path, **_kwargs: FakeKey(path))
    monkeypatch.setattr(service.winreg, "QueryValueEx", lambda _key, _name: (r"C:\Missing\App.exe", service.winreg.REG_SZ))
    monkeypatch.setattr(service, "_file_exists", lambda _path: False)

    item = _check_app_path("HKCU", r"Software\Microsoft\Windows\CurrentVersion\App Paths\App.exe", "App.exe")

    assert item is not None
    assert item.rule_id == "app_path_missing_exe"
    assert item.source == "AppPaths"
    assert item.target_path == r"C:\Missing\App.exe"


def test_check_file_association_missing_open_command_is_review_only(monkeypatch):
    def fake_open_key(_hive, path, **_kwargs):
        return FakeKey(path)

    def fake_query_value(key, _name):
        if key.path == ".demo":
            return ("demo.file", service.winreg.REG_SZ)
        return (r'"C:\Missing\Viewer.exe" "%1"', service.winreg.REG_SZ)

    monkeypatch.setattr(service.winreg, "OpenKey", fake_open_key)
    monkeypatch.setattr(service.winreg, "QueryValueEx", fake_query_value)
    monkeypatch.setattr(service, "_file_exists", lambda _path: False)

    item = _check_file_association("HKCR", ".demo")

    assert item is not None
    assert item.category == "FileAssociation"
    assert item.confidence == "Low"
    assert item.skip_reason == "manual_review_required"
    assert item.selected is False


def test_check_scheduled_task_file_missing_command_is_review_only(tmp_path, monkeypatch):
    task_file = tmp_path / "DemoTask"
    task_file.write_text(
        """<?xml version="1.0" encoding="UTF-16"?>
<Task><Actions><Exec><Command>C:\\Missing\\task.exe</Command></Exec></Actions></Task>
""",
        encoding="utf-16",
    )
    monkeypatch.setattr(service, "_file_exists", lambda _path: False)

    item = _check_scheduled_task_file(task_file)

    assert item is not None
    assert item.rule_id == "scheduled_task_missing_exe"
    assert item.source == "ScheduledTask"
    assert item.confidence == "Low"
    assert item.skip_reason == "diagnostic_only"
    assert item.selected is False
