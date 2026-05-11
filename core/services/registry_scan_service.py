"""
Registry scan service: 4-phase algorithm
  Phase 1 – CollectKeys   : enumerate registry values from scope roots
  Phase 2 – ResolveTargets: expand env vars, extract executable paths
  Phase 3 – RuleEngine    : match rules, produce issue items
  Phase 4 – RiskScoring   : apply risk model (BaseRisk + ContextRisk + SystemCriticality)
"""

import hashlib
import os
import re
import shutil
import time
import winreg
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

from core.registry_models import RegistryIssueItem, RegistryScannerReport

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HIVE_MAP: dict[str, int] = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
    "HKU":  winreg.HKEY_USERS,
    "HKCC": winreg.HKEY_CURRENT_CONFIG,
}

HIVE_FULL_NAMES: dict[int, str] = {
    winreg.HKEY_CURRENT_USER:   "HKEY_CURRENT_USER",
    winreg.HKEY_LOCAL_MACHINE:  "HKEY_LOCAL_MACHINE",
    winreg.HKEY_CLASSES_ROOT:   "HKEY_CLASSES_ROOT",
    winreg.HKEY_USERS:          "HKEY_USERS",
    winreg.HKEY_CURRENT_CONFIG: "HKEY_CURRENT_CONFIG",
}

_SYSTEM_ROOT = os.environ.get("SystemRoot", r"C:\Windows").lower()
_SYSTEM32   = os.path.join(_SYSTEM_ROOT, "system32")
_SYSWOW64   = os.path.join(_SYSTEM_ROOT, "syswow64")

SYSTEM_CRITICAL_SERVICES = {
    "windefend", "w32time", "eventlog", "rpcss", "dcomlaunch",
    "lsass", "plugplay", "power", "profsvcs", "schedule", "seclogon",
    "sens", "winmgmt", "wuauserv", "bits", "cryptsvc", "dnscache",
    "lanmanserver", "lanmanworkstation", "mpssvc", "netlogon", "nsi",
    "samss", "spooler", "themes", "trustedinstaller", "wlansvc",
    "msiserver", "appinfo", "base filtering engine", "bfe",
}

# Standard scope roots: (hive_short, key_path, scan_type)
STANDARD_ROOTS = [
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run",     "startup"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "startup"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Run",     "startup"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "startup"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Uninstall",                      "uninstall"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Uninstall",                      "uninstall"),
    ("HKLM", r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",          "uninstall"),
]

EXTENDED_EXTRA_ROOTS = [
    ("HKLM", r"SYSTEM\CurrentControlSet\Services", "service"),
    ("HKCR", r"CLSID",                             "clsid"),
    ("HKCR", r"WOW6432Node\CLSID",                 "clsid"),
    ("HKCR", r"TypeLib",                           "typelib"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\App Paths", "app_paths"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\App Paths", "app_paths"),
    ("HKCR", r"",                                  "file_assoc"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run", "startup_approved"),
    ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run", "startup_approved"),
    ("HKCC", r"ScheduledTasks",                    "scheduled_task"),
]

MAX_CLSID_PER_HIVE = 3000
MAX_TYPELIB_ITEMS = 3000
MAX_FILE_ASSOC_ITEMS = 1500
MAX_SCHEDULED_TASK_ITEMS = 3000
SCHEDULED_TASK_ROOT = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "Tasks"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _expand_path(raw: str) -> str:
    raw = raw.strip()
    raw = os.path.expandvars(raw)
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    if raw.lower().startswith("\\systemroot\\"):
        raw = system_root + raw[len("\\systemroot"):]
    elif raw.lower().startswith("system32\\") or raw.lower().startswith("system32/"):
        raw = os.path.join(system_root, raw)
    return raw


def _extract_exe(value_data: str) -> Optional[str]:
    if not value_data:
        return None
    expanded = _expand_path(value_data)
    # Quoted path: "C:\path\app.exe" [args]
    if expanded.startswith('"'):
        end = expanded.find('"', 1)
        if end > 1:
            return expanded[1:end]
        return expanded[1:]
    # Match up to first .exe or .dll (case-insensitive)
    m = re.match(r'^(.*?\.(?:exe|dll|com|bat|cmd|ps1))', expanded, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fall back: first token
    return expanded.split()[0] if expanded else None


def _strip_invocation_noise(path: str) -> str:
    value = path.strip().strip('"').strip()
    if "," in value:
        value = value.split(",", 1)[0].strip()
    return value


def _extract_path_references(value_data: str) -> list[str]:
    if not value_data:
        return []

    expanded = _expand_path(value_data)
    refs: list[str] = []

    for quoted in re.findall(r'"([^"]+\.(?:exe|dll|com|bat|cmd|ps1))"', expanded, re.IGNORECASE):
        refs.append(_strip_invocation_noise(quoted))

    for match in re.findall(r'([A-Za-z]:\\[^\s"]+\.(?:exe|dll|com|bat|cmd|ps1))', expanded, re.IGNORECASE):
        refs.append(_strip_invocation_noise(match))

    first = _extract_exe(expanded)
    if first:
        refs.append(_strip_invocation_noise(first))

    unique: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        key = ref.lower()
        if ref and key not in seen:
            seen.add(key)
            unique.append(ref)
    return unique


def _file_exists(path: Optional[str]) -> bool:
    if not path:
        return True  # no path → skip, not an issue
    if "\\" not in path and "/" not in path:
        return shutil.which(path) is not None
    try:
        return Path(path).exists()
    except (ValueError, OSError):
        return True


def _validation_status(path: Optional[str]) -> str:
    if not path:
        return "no_target"
    if "\\" not in path and "/" not in path:
        return "command_found" if shutil.which(path) else "command_missing"
    try:
        return "path_exists" if Path(path).exists() else "path_missing"
    except (ValueError, OSError):
        return "unverifiable_path"


def _confidence_for_issue(category: str, target_path: Optional[str], hive_short: str) -> str:
    status = _validation_status(target_path)
    if status == "unverifiable_path":
        return "Low"
    if category in {"OrphanCOM", "InvalidService", "FileAssociation"}:
        return "Low"
    if category == "InvalidUninstall" and hive_short != "HKCU":
        return "Medium"
    if category == "InvalidUninstall":
        return "Medium"
    return "High"


def _default_selected_for_issue(category: str, risk: str, confidence: str, hive_short: str) -> bool:
    return category == "StartupIssue" and risk == "Safe" and confidence == "High" and hive_short == "HKCU"


def _manual_review_reason(category: str, confidence: str, hive_short: str) -> Optional[str]:
    if confidence == "Low":
        return "low_confidence"
    if category in {"InvalidUninstall", "InvalidService", "OrphanCOM"}:
        return "manual_review_required"
    if hive_short != "HKCU":
        return "machine_hive_requires_admin"
    return None


def _make_issue(
    *,
    id: str,
    category: str,
    risk: str,
    source: str,
    hive: str,
    key_path: str,
    value_name: Optional[str],
    value_data: Optional[str],
    target_path: Optional[str],
    description: str,
    rule_id: str,
    is_system_critical: bool = False,
    confidence_override: Optional[str] = None,
    skip_reason_override: Optional[str] = None,
    selected_override: Optional[bool] = None,
) -> RegistryIssueItem:
    confidence = confidence_override or _confidence_for_issue(category, target_path, hive)
    skip_reason = skip_reason_override
    if skip_reason is None:
        skip_reason = _manual_review_reason(category, confidence, hive)
    selected = selected_override
    if selected is None:
        selected = _default_selected_for_issue(category, risk, confidence, hive)
    return RegistryIssueItem(
        id=id,
        category=category,
        risk=risk,
        source=source,
        hive=hive,
        key_path=key_path,
        value_name=value_name,
        value_data=value_data,
        target_path=target_path,
        description=description,
        rule_id=rule_id,
        confidence=confidence,
        validation_status=_validation_status(target_path),
        skip_reason=skip_reason,
        is_system_critical=is_system_critical,
        selected=selected,
    )


def _make_report(hive_short: str, key_path: str, scan_type: str) -> RegistryScannerReport:
    limits = {
        "clsid": MAX_CLSID_PER_HIVE,
        "typelib": MAX_TYPELIB_ITEMS,
        "file_assoc": MAX_FILE_ASSOC_ITEMS,
        "scheduled_task": MAX_SCHEDULED_TASK_ITEMS,
    }
    return RegistryScannerReport(
        hive=hive_short,
        key_path=key_path,
        scan_type=scan_type,
        status="ok",
        limit=limits.get(scan_type),
    )


def _mark_report_error(report: RegistryScannerReport, exc: Exception) -> None:
    report.status = "error"
    report.error = str(exc)


# ---------------------------------------------------------------------------
# Risk model
# ---------------------------------------------------------------------------

def _is_system_path(path: Optional[str]) -> bool:
    if not path:
        return False
    p = path.lower()
    return p.startswith(_SYSTEM32) or p.startswith(_SYSWOW64)


def _score_risk(
    base_risk: str,
    target_path: Optional[str],
    hive_short: str,
    key_path: str,
    service_name: Optional[str] = None,
) -> tuple[str, bool]:
    """Returns (risk_level, is_system_critical)."""
    # System criticality overrides everything
    if _is_system_path(target_path):
        return "High", True
    if service_name and service_name.lower() in SYSTEM_CRITICAL_SERVICES:
        return "High", True
    if "CurrentControlSet\\Services" in key_path:
        seg = key_path.split("\\")[-1].lower()
        if seg in SYSTEM_CRITICAL_SERVICES:
            return "High", True

    # Context risk adjustment
    context = 0
    if target_path:
        p = target_path.lower()
        if p.startswith(_SYSTEM_ROOT):
            context += 1
    if hive_short == "HKLM" and "CurrentControlSet\\Services" in key_path:
        context += 1

    risk_order = ["Safe", "Medium", "High"]
    idx = risk_order.index(base_risk)
    final_idx = min(idx + context, 2)
    return risk_order[final_idx], False


def _make_id(*parts: str) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Phase helpers per scan type
# ---------------------------------------------------------------------------

def _read_value(key_handle, name: str) -> Optional[str]:
    try:
        val, _ = winreg.QueryValueEx(key_handle, name)
        return str(val).strip() if val is not None else None
    except (OSError, ValueError):
        return None


def _scan_startup(hive_short: str, key_path: str, mode: str, report: RegistryScannerReport) -> list[RegistryIssueItem]:
    results: list[RegistryIssueItem] = []
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ) as key:
            idx = 0
            while True:
                try:
                    name, data, _ = winreg.EnumValue(key, idx)
                    idx += 1
                    report.checked += 1
                except OSError:
                    break
                exe = _extract_exe(str(data))
                if _file_exists(exe):
                    report.skipped += 1
                    continue
                risk, critical = _score_risk("Safe", exe, hive_short, key_path)
                if mode == "Safe" and critical:
                    report.skipped += 1
                    continue
                results.append(_make_issue(
                    id=_make_id(hive_short, key_path, name, "StartupIssue"),
                    category="StartupIssue",
                    risk=risk,
                    source="Startup",
                    hive=hive_short,
                    key_path=key_path,
                    value_name=name,
                    value_data=str(data),
                    target_path=exe,
                    description=f"Startup item '{name}' points to missing file",
                    rule_id="startup_missing_target",
                    is_system_critical=critical,
                ))
    except (PermissionError, OSError, FileNotFoundError, ValueError) as exc:
        _mark_report_error(report, exc)
    report.issues = len(results)
    return results


def _scan_uninstall(hive_short: str, key_path: str, mode: str, report: RegistryScannerReport) -> list[RegistryIssueItem]:
    results: list[RegistryIssueItem] = []
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ) as root:
            idx = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(root, idx)
                    idx += 1
                    report.checked += 1
                except OSError:
                    break
                subkey_path = f"{key_path}\\{subkey_name}"
                item = _check_uninstall(hive_short, subkey_path, subkey_name, mode)
                if item:
                    results.append(item)
                else:
                    report.skipped += 1
    except (PermissionError, OSError, FileNotFoundError, ValueError) as exc:
        _mark_report_error(report, exc)
    report.issues = len(results)
    return results


def _check_uninstall(
    hive_short: str, subkey_path: str, app_name: str, mode: str
) -> Optional[RegistryIssueItem]:
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, subkey_path, access=winreg.KEY_READ) as key:
            uninstall_str  = _read_value(key, "UninstallString")
            install_loc    = _read_value(key, "InstallLocation")
            display_icon   = _read_value(key, "DisplayIcon")
            system_component = _read_value(key, "SystemComponent")

            # Skip Windows system components
            if system_component == "1":
                return None

            paths: list[str] = []
            if uninstall_str:
                paths.extend(_extract_path_references(uninstall_str))
            if install_loc:
                paths.append(install_loc)

            if not paths:
                return None
            if any(_file_exists(p) for p in paths):
                return None

            main_path = paths[0]
            risk, critical = _score_risk("Safe", main_path, hive_short, subkey_path)
            if mode == "Safe" and critical:
                return None
            return _make_issue(
                id=_make_id(hive_short, subkey_path, None, "InvalidUninstall"),
                category="InvalidUninstall",
                risk=risk,
                source="Uninstall",
                hive=hive_short,
                key_path=subkey_path,
                value_name=None,
                value_data=uninstall_str,
                target_path=main_path,
                description=f"Uninstall entry '{app_name}' references missing files",
                rule_id="uninstall_missing_target",
                is_system_critical=critical,
            )
    except (PermissionError, OSError, ValueError):
        return None


def _scan_services(hive_short: str, key_path: str, mode: str, report: RegistryScannerReport) -> list[RegistryIssueItem]:
    results: list[RegistryIssueItem] = []
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ) as root:
            idx = 0
            while True:
                try:
                    svc_name = winreg.EnumKey(root, idx)
                    idx += 1
                    report.checked += 1
                except OSError:
                    break
                if svc_name.lower() in SYSTEM_CRITICAL_SERVICES:
                    report.skipped += 1
                    continue
                svc_path = f"{key_path}\\{svc_name}"
                item = _check_service(hive_short, svc_path, svc_name, mode)
                if item:
                    results.append(item)
                else:
                    report.skipped += 1
    except (PermissionError, OSError, FileNotFoundError, ValueError) as exc:
        _mark_report_error(report, exc)
    report.issues = len(results)
    return results


def _check_service(
    hive_short: str, subkey_path: str, svc_name: str, mode: str
) -> Optional[RegistryIssueItem]:
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, subkey_path, access=winreg.KEY_READ) as key:
            image_path = _read_value(key, "ImagePath")
            if not image_path:
                return None
            # Skip kernel/FS driver types (1, 2, 4, 8)
            try:
                svc_type, _ = winreg.QueryValueEx(key, "Type")
                if int(svc_type) in (1, 2, 4, 8):
                    return None
            except OSError:
                pass
            exe = _extract_exe(image_path)
            if _file_exists(exe):
                return None
            risk, critical = _score_risk("Medium", exe, hive_short, subkey_path, svc_name)
            if mode == "Safe" and critical:
                return None
            return _make_issue(
                id=_make_id(hive_short, subkey_path, "ImagePath", "InvalidService"),
                category="InvalidService",
                risk=risk,
                source="Service",
                hive=hive_short,
                key_path=subkey_path,
                value_name="ImagePath",
                value_data=image_path,
                target_path=exe,
                description=f"Service '{svc_name}' executable is missing",
                rule_id="service_missing_exe",
                is_system_critical=critical,
            )
    except (PermissionError, OSError, ValueError):
        return None


def _scan_clsid(hive_short: str, key_path: str, mode: str, report: RegistryScannerReport) -> list[RegistryIssueItem]:
    results: list[RegistryIssueItem] = []
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ) as root:
            idx = 0
            while idx < MAX_CLSID_PER_HIVE:
                try:
                    clsid = winreg.EnumKey(root, idx)
                    idx += 1
                    report.checked += 1
                except OSError:
                    break
                items = _check_clsid(hive_short, key_path, clsid, mode)
                if items:
                    results.extend(items)
                else:
                    report.skipped += 1
            report.truncated = idx >= MAX_CLSID_PER_HIVE
    except (PermissionError, OSError, FileNotFoundError, ValueError) as exc:
        _mark_report_error(report, exc)
    report.issues = len(results)
    return results


def _check_clsid(
    hive_short: str, clsid_root: str, clsid: str, mode: str
) -> list[RegistryIssueItem]:
    items: list[RegistryIssueItem] = []
    inproc_path = f"{clsid_root}\\{clsid}\\InprocServer32"
    local_server_path = f"{clsid_root}\\{clsid}\\LocalServer32"
    inproc_item = _check_com_server(
        hive_short=hive_short,
        server_key_path=inproc_path,
        clsid=clsid,
        mode=mode,
        server_kind="InprocServer32",
        rule_id="com_missing_dll",
        target_label="DLL",
    )
    if inproc_item:
        items.append(inproc_item)
    local_server_item = _check_com_server(
        hive_short=hive_short,
        server_key_path=local_server_path,
        clsid=clsid,
        mode=mode,
        server_kind="LocalServer32",
        rule_id="com_missing_local_server",
        target_label="local server executable",
    )
    if local_server_item:
        items.append(local_server_item)
    treat_as_item = _check_com_treat_as(hive_short, clsid_root, clsid)
    if treat_as_item:
        items.append(treat_as_item)
    return items


def _check_com_server(
    *,
    hive_short: str,
    server_key_path: str,
    clsid: str,
    mode: str,
    server_kind: str,
    rule_id: str,
    target_label: str,
) -> Optional[RegistryIssueItem]:
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, server_key_path, access=winreg.KEY_READ) as key:
            raw_path = _read_value(key, "")  # default value
            if not raw_path:
                return None
            target_path = _extract_exe(raw_path) if server_kind == "LocalServer32" else _expand_path(raw_path)
            if _file_exists(target_path):
                return None
            risk, critical = _score_risk("Medium", target_path, hive_short, server_key_path)
            if mode == "Safe" and critical:
                return None
            return _make_issue(
                id=_make_id(hive_short, server_key_path, "", "OrphanCOM"),
                category="OrphanCOM",
                risk=risk,
                source="COM",
                hive=hive_short,
                key_path=server_key_path,
                value_name="",
                value_data=raw_path,
                target_path=target_path,
                description=f"COM component {clsid} {server_kind} references missing {target_label}",
                rule_id=rule_id,
                is_system_critical=critical,
            )
    except (PermissionError, OSError, ValueError):
        return None


def _check_com_treat_as(hive_short: str, clsid_root: str, clsid: str) -> Optional[RegistryIssueItem]:
    hive = HIVE_MAP[hive_short]
    treat_as_path = f"{clsid_root}\\{clsid}\\TreatAs"
    try:
        with winreg.OpenKey(hive, treat_as_path, access=winreg.KEY_READ) as key:
            target_clsid = _read_value(key, "")
            if not target_clsid:
                return None
        target_path = f"{clsid_root}\\{target_clsid}"
        try:
            with winreg.OpenKey(hive, target_path, access=winreg.KEY_READ):
                return None
        except (PermissionError, OSError, ValueError):
            return _make_issue(
                id=_make_id(hive_short, treat_as_path, "", "ComTreatAs"),
                category="OrphanCOM",
                risk="Medium",
                source="COM",
                hive=hive_short,
                key_path=treat_as_path,
                value_name="",
                value_data=target_clsid,
                target_path=target_path,
                description=f"COM component {clsid} TreatAs points to missing CLSID {target_clsid}",
                rule_id="com_treat_as_missing_clsid",
                confidence_override="Low",
                skip_reason_override="diagnostic_only",
                selected_override=False,
            )
    except (PermissionError, OSError, ValueError):
        return None


def _scan_typelib(hive_short: str, key_path: str, mode: str, report: RegistryScannerReport) -> list[RegistryIssueItem]:
    results: list[RegistryIssueItem] = []
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ) as root:
            idx = 0
            while idx < MAX_TYPELIB_ITEMS:
                try:
                    typelib_id = winreg.EnumKey(root, idx)
                    idx += 1
                    report.checked += 1
                except OSError:
                    break
                results.extend(_scan_typelib_versions(hive_short, key_path, typelib_id))
            report.truncated = idx >= MAX_TYPELIB_ITEMS
    except (PermissionError, OSError, FileNotFoundError, ValueError) as exc:
        _mark_report_error(report, exc)
    report.issues = len(results)
    return results


def _scan_typelib_versions(hive_short: str, root_path: str, typelib_id: str) -> list[RegistryIssueItem]:
    results: list[RegistryIssueItem] = []
    hive = HIVE_MAP[hive_short]
    typelib_path = f"{root_path}\\{typelib_id}"
    try:
        with winreg.OpenKey(hive, typelib_path, access=winreg.KEY_READ) as key:
            idx = 0
            while True:
                try:
                    version = winreg.EnumKey(key, idx)
                    idx += 1
                except OSError:
                    break
                results.extend(_scan_typelib_platforms(hive_short, f"{typelib_path}\\{version}", typelib_id, version))
    except (PermissionError, OSError, ValueError):
        return []
    return results


def _scan_typelib_platforms(hive_short: str, version_path: str, typelib_id: str, version: str) -> list[RegistryIssueItem]:
    results: list[RegistryIssueItem] = []
    hive = HIVE_MAP[hive_short]
    for platform in ("win32", "win64"):
        platform_path = f"{version_path}\\0\\{platform}"
        try:
            with winreg.OpenKey(hive, platform_path, access=winreg.KEY_READ) as key:
                raw_path = _read_value(key, "")
                if not raw_path:
                    continue
                target_path = _expand_path(raw_path)
                if _file_exists(target_path):
                    continue
                results.append(_make_issue(
                    id=_make_id(hive_short, platform_path, "", "ComTypeLib"),
                    category="OrphanCOM",
                    risk="Medium",
                    source="COM",
                    hive=hive_short,
                    key_path=platform_path,
                    value_name="",
                    value_data=raw_path,
                    target_path=target_path,
                    description=f"COM TypeLib {typelib_id} {version} references missing {platform} file",
                    rule_id="com_typelib_missing_file",
                    confidence_override="Low",
                    skip_reason_override="low_confidence",
                    selected_override=False,
                ))
        except (PermissionError, OSError, ValueError):
            continue
    return results


def _scan_app_paths(hive_short: str, key_path: str, mode: str, report: RegistryScannerReport) -> list[RegistryIssueItem]:
    results: list[RegistryIssueItem] = []
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ) as root:
            idx = 0
            while True:
                try:
                    app_name = winreg.EnumKey(root, idx)
                    idx += 1
                    report.checked += 1
                except OSError:
                    break
                item = _check_app_path(hive_short, f"{key_path}\\{app_name}", app_name)
                if item:
                    results.append(item)
                else:
                    report.skipped += 1
    except (PermissionError, OSError, FileNotFoundError, ValueError) as exc:
        _mark_report_error(report, exc)
    report.issues = len(results)
    return results


def _check_app_path(hive_short: str, app_key_path: str, app_name: str) -> Optional[RegistryIssueItem]:
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, app_key_path, access=winreg.KEY_READ) as key:
            raw_path = _read_value(key, "")
            if not raw_path:
                return None
            target_path = _extract_exe(raw_path)
            if _file_exists(target_path):
                return None
            risk, critical = _score_risk("Safe", target_path, hive_short, app_key_path)
            return _make_issue(
                id=_make_id(hive_short, app_key_path, "", "AppPath"),
                category="InvalidPath",
                risk=risk,
                source="AppPaths",
                hive=hive_short,
                key_path=app_key_path,
                value_name="",
                value_data=raw_path,
                target_path=target_path,
                description=f"App Path entry '{app_name}' points to missing executable",
                rule_id="app_path_missing_exe",
                is_system_critical=critical,
                confidence_override="Low" if hive_short != "HKCU" else None,
                skip_reason_override="machine_hive_requires_admin" if hive_short != "HKCU" else None,
                selected_override=False if hive_short != "HKCU" else None,
            )
    except (PermissionError, OSError, ValueError):
        return None


def _scan_file_associations(hive_short: str, key_path: str, mode: str, report: RegistryScannerReport) -> list[RegistryIssueItem]:
    results: list[RegistryIssueItem] = []
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ) as root:
            idx = 0
            while idx < MAX_FILE_ASSOC_ITEMS:
                try:
                    subkey_name = winreg.EnumKey(root, idx)
                    idx += 1
                except OSError:
                    break
                if not subkey_name.startswith("."):
                    continue
                report.checked += 1
                item = _check_file_association(hive_short, subkey_name)
                if item:
                    results.append(item)
                else:
                    report.skipped += 1
            report.truncated = idx >= MAX_FILE_ASSOC_ITEMS
    except (PermissionError, OSError, FileNotFoundError, ValueError) as exc:
        _mark_report_error(report, exc)
    report.issues = len(results)
    return results


def _check_file_association(hive_short: str, extension: str) -> Optional[RegistryIssueItem]:
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, extension, access=winreg.KEY_READ) as ext_key:
            prog_id = _read_value(ext_key, "")
            if not prog_id:
                return None
        command_path = f"{prog_id}\\shell\\open\\command"
        with winreg.OpenKey(hive, command_path, access=winreg.KEY_READ) as cmd_key:
            command = _read_value(cmd_key, "")
            if not command:
                return None
            target_path = _extract_exe(command)
            if _file_exists(target_path):
                return None
            return _make_issue(
                id=_make_id(hive_short, command_path, "", "FileAssociation"),
                category="FileAssociation",
                risk="Medium",
                source="FileAssociation",
                hive=hive_short,
                key_path=command_path,
                value_name="",
                value_data=command,
                target_path=target_path,
                description=f"File association '{extension}' command references missing executable",
                rule_id="file_assoc_missing_open_command",
                confidence_override="Low",
                skip_reason_override="manual_review_required",
                selected_override=False,
            )
    except (PermissionError, OSError, ValueError):
        return None


def _scan_startup_approved(hive_short: str, key_path: str, mode: str, report: RegistryScannerReport) -> list[RegistryIssueItem]:
    results: list[RegistryIssueItem] = []
    run_key = key_path.rsplit("\\Explorer\\StartupApproved", 1)[0] + r"\Run"
    hive = HIVE_MAP[hive_short]
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ) as key:
            idx = 0
            while True:
                try:
                    name, data, _ = winreg.EnumValue(key, idx)
                    idx += 1
                    report.checked += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(hive, run_key, access=winreg.KEY_READ) as run:
                        _read_value(run, name)
                        if _read_value(run, name) is not None:
                            report.skipped += 1
                            continue
                except (PermissionError, OSError, ValueError):
                    pass
                results.append(_make_issue(
                    id=_make_id(hive_short, key_path, name, "StartupApproved"),
                    category="StartupIssue",
                    risk="Safe",
                    source="StartupApproved",
                    hive=hive_short,
                    key_path=key_path,
                    value_name=name,
                    value_data=str(data),
                    target_path=None,
                    description=f"StartupApproved entry '{name}' has no matching Run entry",
                    rule_id="startup_approved_orphan_entry",
                    confidence_override="Low",
                    skip_reason_override="diagnostic_only",
                    selected_override=False,
                ))
    except (PermissionError, OSError, FileNotFoundError, ValueError) as exc:
        _mark_report_error(report, exc)
    report.issues = len(results)
    return results


def _scan_scheduled_tasks(hive_short: str, key_path: str, mode: str, report: RegistryScannerReport) -> list[RegistryIssueItem]:
    results: list[RegistryIssueItem] = []
    if not SCHEDULED_TASK_ROOT.exists():
        report.status = "skipped"
        return results
    try:
        for task_file in SCHEDULED_TASK_ROOT.rglob("*"):
            if report.checked >= MAX_SCHEDULED_TASK_ITEMS:
                report.truncated = True
                break
            if not task_file.is_file():
                continue
            report.checked += 1
            item = _check_scheduled_task_file(task_file)
            if item:
                results.append(item)
            else:
                report.skipped += 1
    except (OSError, ValueError) as exc:
        _mark_report_error(report, exc)
    report.issues = len(results)
    return results


def _check_scheduled_task_file(task_file: Path) -> Optional[RegistryIssueItem]:
    try:
        root = ET.parse(task_file).getroot()
    except (ET.ParseError, OSError, ValueError):
        return None
    commands = [
        (node.text or "").strip()
        for node in root.iter()
        if node.tag.lower().endswith("command") and (node.text or "").strip()
    ]
    for command in commands:
        target_path = _extract_exe(command)
        if _file_exists(target_path):
            continue
        return _make_issue(
            id=_make_id("TASK", str(task_file), command, "ScheduledTask"),
            category="StartupIssue",
            risk="Safe",
            source="ScheduledTask",
            hive="HKCC",
            key_path=str(task_file),
            value_name="Command",
            value_data=command,
            target_path=target_path,
            description=f"Scheduled task '{task_file.name}' references missing executable",
            rule_id="scheduled_task_missing_exe",
            confidence_override="Low",
            skip_reason_override="diagnostic_only",
            selected_override=False,
        )
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_registry(scope: str = "Standard", mode: str = "Safe") -> dict:
    """
    Run the 4-phase registry scan and return {issues, stats}.

    scope: "Standard" | "Extended"
    mode:  "Safe"     | "Advanced"
    """
    roots = list(STANDARD_ROOTS)
    if scope == "Extended":
        roots += EXTENDED_EXTRA_ROOTS

    issues: list[RegistryIssueItem] = []
    reports: list[RegistryScannerReport] = []

    for hive_short, key_path, scan_type in roots:
        report = _make_report(hive_short, key_path, scan_type)
        started = time.perf_counter()
        if scan_type == "startup":
            issues += _scan_startup(hive_short, key_path, mode, report)
        elif scan_type == "uninstall":
            issues += _scan_uninstall(hive_short, key_path, mode, report)
        elif scan_type == "service":
            issues += _scan_services(hive_short, key_path, mode, report)
        elif scan_type == "clsid":
            issues += _scan_clsid(hive_short, key_path, mode, report)
        elif scan_type == "typelib":
            issues += _scan_typelib(hive_short, key_path, mode, report)
        elif scan_type == "app_paths":
            issues += _scan_app_paths(hive_short, key_path, mode, report)
        elif scan_type == "file_assoc":
            issues += _scan_file_associations(hive_short, key_path, mode, report)
        elif scan_type == "startup_approved":
            issues += _scan_startup_approved(hive_short, key_path, mode, report)
        elif scan_type == "scheduled_task":
            issues += _scan_scheduled_tasks(hive_short, key_path, mode, report)
        report.duration_ms = int((time.perf_counter() - started) * 1000)
        reports.append(report)

    # De-duplicate by id (same key may appear in multiple roots)
    seen: set[str] = set()
    unique: list[RegistryIssueItem] = []
    for item in issues:
        if item.id not in seen:
            seen.add(item.id)
            unique.append(item)

    stats = _build_stats(unique)
    return {"issues": unique, "stats": stats, "reports": reports}


def _build_stats(issues: list[RegistryIssueItem]) -> dict:
    by_risk: dict[str, int] = {"Safe": 0, "Medium": 0, "High": 0}
    by_category: dict[str, int] = {}
    by_confidence: dict[str, int] = {"High": 0, "Medium": 0, "Low": 0}
    by_validation_status: dict[str, int] = {}
    for item in issues:
        by_risk[item.risk] = by_risk.get(item.risk, 0) + 1
        by_category[item.category] = by_category.get(item.category, 0) + 1
        by_confidence[item.confidence] = by_confidence.get(item.confidence, 0) + 1
        by_validation_status[item.validation_status] = by_validation_status.get(item.validation_status, 0) + 1
    return {
        "total": len(issues),
        "by_risk": by_risk,
        "by_category": by_category,
        "by_confidence": by_confidence,
        "by_validation_status": by_validation_status,
    }
