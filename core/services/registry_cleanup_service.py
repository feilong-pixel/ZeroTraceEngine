"""
Registry cleanup service:
  - generate_registry_plan : export .reg backups + create plan record
  - execute_registry_plan  : delete registry entries (requires plan already generated)
  - restore_registry_plan  : re-import .reg files via reg.exe
"""

import json
import re
import subprocess
import uuid
import winreg
import ctypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.config import settings
from core.models import CleanRecord
from core.registry_models import RegistryCleanupAction, RegistryCleanupPlan, RegistryIssueItem
from core.services.registry_scan_service import HIVE_FULL_NAMES, HIVE_MAP
from core.storage.clean_log_repository import insert_clean_records
from core.storage.registry_cleanup_repository import (
    load_plan,
    save_plan,
    update_plan_status,
)
from core.storage.registry_scan_repository import load_registry_scan_results

# Root dir for registry recycle bin
REGISTRY_RECYCLE_ROOT = settings.recycle_root.parent / "ZeroTraceRegistryRecycle"
ADMIN_REQUIRED_HIVES = {"HKLM", "HKCR", "HKU", "HKCC"}


# ---------------------------------------------------------------------------
# .reg file helpers
# ---------------------------------------------------------------------------

def _escape_reg_str(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _format_reg_value(name: Optional[str], data, reg_type: int) -> str:
    name_part = "@" if not name else f'"{_escape_reg_str(name)}"'

    if reg_type == winreg.REG_SZ:
        return f'{name_part}="{_escape_reg_str(str(data))}"'
    if reg_type == winreg.REG_EXPAND_SZ:
        encoded = (str(data) + "\x00").encode("utf-16-le")
        hex_str = ",".join(f"{b:02x}" for b in encoded)
        return f"{name_part}=hex(2):{hex_str}"
    if reg_type == winreg.REG_DWORD:
        return f"{name_part}=dword:{int(data):08x}"
    if reg_type == winreg.REG_QWORD:
        encoded = int(data).to_bytes(8, "little")
        hex_str = ",".join(f"{b:02x}" for b in encoded)
        return f"{name_part}=hex(b):{hex_str}"
    if reg_type == winreg.REG_MULTI_SZ:
        joined = "\x00".join(data) + "\x00\x00" if data else "\x00\x00"
        encoded = joined.encode("utf-16-le")
        hex_str = ",".join(f"{b:02x}" for b in encoded)
        return f"{name_part}=hex(7):{hex_str}"
    if reg_type == winreg.REG_BINARY and isinstance(data, bytes):
        hex_str = ",".join(f"{b:02x}" for b in data)
        return f"{name_part}=hex:{hex_str}"
    return f'{name_part}="{_escape_reg_str(str(data))}"'


def _export_to_reg_content(action: RegistryCleanupAction) -> str:
    """Build .reg file content (string, caller encodes as UTF-16 LE + BOM)."""
    hive_handle = HIVE_MAP[action.hive]
    hive_name   = HIVE_FULL_NAMES[hive_handle]
    full_path   = f"{hive_name}\\{action.key_path}"
    lines       = ["Windows Registry Editor Version 5.00", "", f"[{full_path}]"]

    try:
        with winreg.OpenKey(hive_handle, action.key_path, access=winreg.KEY_READ) as key:
            if action.value_name is not None:
                # Export specific named value
                try:
                    data, reg_type = winreg.QueryValueEx(key, action.value_name)
                    lines.append(_format_reg_value(action.value_name, data, reg_type))
                except OSError:
                    pass
            else:
                # Export all values (for subkey-level entries like Uninstall)
                idx = 0
                while True:
                    try:
                        name, data, reg_type = winreg.EnumValue(key, idx)
                        idx += 1
                        lines.append(_format_reg_value(name, data, reg_type))
                    except OSError:
                        break
    except (PermissionError, OSError):
        pass

    return "\r\n".join(lines) + "\r\n"


def _safe_filename(hive: str, key_path: str, value_name: Optional[str]) -> str:
    last_seg = key_path.split("\\")[-1]
    parts    = [hive, last_seg]
    if value_name is not None and value_name != "":
        parts.append(value_name)
    name = "_".join(parts)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return f"{name}.reg"


def is_running_as_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def get_registry_capabilities() -> dict:
    is_admin = is_running_as_admin()
    return {
        "is_admin": is_admin,
        "can_write_machine_hives": is_admin,
        "admin_required_hives": sorted(ADMIN_REQUIRED_HIVES),
    }


# ---------------------------------------------------------------------------
# Registry deletion helpers
# ---------------------------------------------------------------------------

def _delete_registry_value(hive_short: str, key_path: str, value_name: str) -> None:
    hive = HIVE_MAP[hive_short]
    with winreg.OpenKey(hive, key_path, access=winreg.KEY_SET_VALUE) as key:
        winreg.DeleteValue(key, value_name)


def _delete_registry_key(hive_short: str, key_path: str) -> None:
    """Delete a registry key (leaf). Parent path inferred from key_path."""
    hive = HIVE_MAP[hive_short]
    parts       = key_path.rsplit("\\", 1)
    parent_path = parts[0] if len(parts) == 2 else ""
    key_name    = parts[-1]
    with winreg.OpenKey(hive, parent_path, access=winreg.KEY_SET_VALUE | winreg.KEY_READ) as parent:
        winreg.DeleteKey(parent, key_name)


def _format_delete_error(action: RegistryCleanupAction, exc: Exception) -> str:
    target = f"{action.hive}\\{action.key_path}"
    if action.value_name is not None:
        target = f"{target}\\{action.value_name}"
    hint = ""
    if isinstance(exc, PermissionError):
        hint = " (permission denied; HKLM/HKCR entries usually require running as Administrator)"
    return f"{target}: {exc}{hint}"


def _admin_required_actions(actions: list[RegistryCleanupAction]) -> list[RegistryCleanupAction]:
    return [action for action in actions if action.hive in ADMIN_REQUIRED_HIVES]


def _load_plan_meta(plan: RegistryCleanupPlan) -> dict:
    meta_path = Path(plan.plan_dir) / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _review_required_meta_actions(plan: RegistryCleanupPlan) -> list[dict]:
    meta = _load_plan_meta(plan)
    return [
        action
        for action in meta.get("actions", [])
        if action.get("confidence") == "Low" or action.get("skipReason")
    ]


def _review_action_ids(plan: RegistryCleanupPlan) -> set[str]:
    return {
        str(action.get("id"))
        for action in _review_required_meta_actions(plan)
        if action.get("id")
    }


def _diagnostic_only_meta_actions(plan: RegistryCleanupPlan) -> list[dict]:
    meta = _load_plan_meta(plan)
    return [
        action
        for action in meta.get("actions", [])
        if action.get("skipReason") == "diagnostic_only"
    ]


def _read_backup_reg_content(plan: RegistryCleanupPlan, action: RegistryCleanupAction) -> str | None:
    reg_path = Path(plan.plan_dir) / action.reg_file
    if not reg_path.exists():
        return None
    try:
        content = reg_path.read_bytes()
    except OSError:
        return None
    if content.startswith(b"\xff\xfe"):
        content = content[2:]
    try:
        return content.decode("utf-16-le")
    except UnicodeDecodeError:
        return None


def _snapshot_mismatches(plan: RegistryCleanupPlan) -> list[str]:
    mismatches: list[str] = []
    for action in plan.actions:
        backup_content = _read_backup_reg_content(plan, action)
        current_content = _export_to_reg_content(action)
        if backup_content is None:
            mismatches.append(f"{action.hive}\\{action.key_path}: backup snapshot is missing or unreadable")
            continue
        if current_content != backup_content:
            mismatches.append(f"{action.hive}\\{action.key_path}: registry entry changed after the plan was generated")
    return mismatches


def _restore_preview(plan: RegistryCleanupPlan) -> dict:
    items: list[dict] = []
    overwrite_count = 0
    missing_backup_count = 0
    for action in plan.actions:
        backup_content = _read_backup_reg_content(plan, action)
        current_content = _export_to_reg_content(action)
        will_overwrite = backup_content is not None and current_content != backup_content
        if backup_content is None:
            missing_backup_count += 1
        if will_overwrite:
            overwrite_count += 1
        items.append({
            "id": action.id,
            "hive": action.hive,
            "key_path": action.key_path,
            "value_name": action.value_name,
            "reg_file": action.reg_file,
            "backup_path": str(Path(plan.plan_dir) / action.reg_file),
            "will_overwrite": will_overwrite,
            "backup_missing": backup_content is None,
        })
    return {
        "ok": True,
        "plan_id": plan.plan_id,
        "action_count": len(plan.actions),
        "overwrite_count": overwrite_count,
        "missing_backup_count": missing_backup_count,
        "requires_confirmation": overwrite_count > 0 or missing_backup_count > 0,
        "items": items,
    }


def _registry_audit_record(
    *,
    action: RegistryCleanupAction,
    plan: RegistryCleanupPlan,
    operation_type: str,
    timestamp: datetime,
) -> CleanRecord:
    target = f"{action.hive}\\{action.key_path}"
    if action.value_name is not None:
        target = f"{target}\\{action.value_name}"
    return CleanRecord(
        id=uuid.uuid4().hex,
        unique_id=action.id,
        original_path=target,
        recycle_path=str(Path(plan.plan_dir) / action.reg_file),
        size=0,
        file_type="registry",
        category=action.category,
        source="registry",
        scanner="RegistryCleanupService",
        risk_level=action.risk.lower(),
        hash=plan.plan_id,
        operation_type=operation_type,
        deleted_at=timestamp,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_registry_plan(issue_ids: list[str]) -> dict:
    """
    From a list of RegistryIssueItem IDs (as selected by the user):
      1. Load matching issues from DB
      2. Export .reg backup files into ZeroTraceRegistryRecycle/{date}/{plan_id}/
      3. Write meta.json
      4. Save plan to DB
      5. Return plan summary (does NOT yet delete anything)
    """
    all_issues = load_registry_scan_results()
    id_set     = set(issue_ids)
    selected   = [i for i in all_issues if i.id in id_set]

    if not selected:
        raise ValueError("No matching registry issues found for the provided IDs")

    plan_id  = uuid.uuid4().hex
    now      = datetime.now(timezone.utc).isoformat()
    date_str = datetime.now().strftime("%Y%m%d")
    plan_dir = REGISTRY_RECYCLE_ROOT / date_str / plan_id
    plan_dir.mkdir(parents=True, exist_ok=True)

    risk_summary: dict[str, int] = {"Safe": 0, "Medium": 0, "High": 0}
    actions: list[RegistryCleanupAction] = []
    issue_by_action_id: dict[str, RegistryIssueItem] = {}

    for item in selected:
        risk_summary[item.risk] = risk_summary.get(item.risk, 0) + 1
        reg_filename = _safe_filename(item.hive, item.key_path, item.value_name)
        action_id = uuid.uuid4().hex
        action = RegistryCleanupAction(
            id=action_id,
            plan_id=plan_id,
            hive=item.hive,
            key_path=item.key_path,
            value_name=item.value_name,
            category=item.category,
            risk=item.risk,
            is_system_critical=item.is_system_critical,
            reg_file=reg_filename,
        )
        # Export .reg backup
        content = _export_to_reg_content(action)
        reg_path = plan_dir / reg_filename
        reg_path.write_bytes(b"\xff\xfe" + content.encode("utf-16-le"))
        actions.append(action)
        issue_by_action_id[action_id] = item

    # Write meta.json
    meta = {
        "planId":      plan_id,
        "createdAt":   now,
        "createdBy":   "ZeroTraceEngine",
        "riskSummary": risk_summary,
        "actions": [
            {
                "id":             a.id,
                "hive":           a.hive,
                "keyPath":        a.key_path,
                "valueName":      a.value_name,
                "category":       a.category,
                "risk":           a.risk,
                "regFile":        a.reg_file,
                "confidence":     issue_by_action_id[a.id].confidence,
                "validationStatus": issue_by_action_id[a.id].validation_status,
                "skipReason":     issue_by_action_id[a.id].skip_reason,
            }
            for a in actions
        ],
    }
    review_action_count = sum(
        1
        for action_meta in meta["actions"]
        if action_meta.get("confidence") == "Low" or action_meta.get("skipReason")
    )
    (plan_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    plan = RegistryCleanupPlan(
        plan_id=plan_id,
        created_at=now,
        risk_summary=risk_summary,
        status="pending",
        plan_dir=str(plan_dir),
        actions=actions,
    )
    save_plan(plan)

    return {
        "ok":           True,
        "plan_id":      plan_id,
        "created_at":   now,
        "risk_summary": risk_summary,
        "action_count": len(actions),
        "review_action_count": review_action_count,
        "review_actions": [
            action_meta
            for action_meta in meta["actions"]
            if action_meta.get("confidence") == "Low" or action_meta.get("skipReason")
        ],
        "can_execute": review_action_count == 0,
        "plan_dir":     str(plan_dir),
    }


def execute_registry_plan(plan_id: str, confirmed_review_action_ids: list[str] | None = None) -> dict:
    """
    Delete registry entries for the given plan (backups already exported at generate time).
    Updates plan status to 'executed'.
    """
    plan = load_plan(plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")
    if plan.status == "executed":
        raise ValueError(f"Plan {plan_id} has already been executed")

    succeeded = 0
    failed    = 0
    errors: list[str] = []
    diagnostic_only = _diagnostic_only_meta_actions(plan)
    if diagnostic_only:
        return {
            "ok":         False,
            "plan_id":    plan_id,
            "succeeded":  0,
            "failed":     len(diagnostic_only),
            "errors": [
                f"{action.get('hive')}\\{action.get('keyPath')}: diagnostic-only registry finding cannot be executed"
                for action in diagnostic_only
            ],
            "executed_at": None,
            "diagnostic_only": True,
        }
    review_required = _review_required_meta_actions(plan)
    required_review_ids = _review_action_ids(plan)
    confirmed_review_ids = set(confirmed_review_action_ids or [])
    missing_review_ids = sorted(required_review_ids - confirmed_review_ids)
    if missing_review_ids:
        return {
            "ok":         False,
            "plan_id":    plan_id,
            "succeeded":  0,
            "failed":     len(missing_review_ids),
            "errors": [
                f"{action.get('hive')}\\{action.get('keyPath')}: review is required before executing this registry plan"
                for action in review_required
                if str(action.get("id")) in missing_review_ids
            ],
            "executed_at": None,
            "requires_review": True,
            "missing_review_action_ids": missing_review_ids,
        }

    admin_required = _admin_required_actions(plan.actions)
    if admin_required and not is_running_as_admin():
        errors = [
            f"{action.hive}\\{action.key_path}: administrator permission is required before deleting this registry entry"
            for action in admin_required
        ]
        return {
            "ok":         False,
            "plan_id":    plan_id,
            "succeeded":  0,
            "failed":     len(admin_required),
            "errors":     errors,
            "executed_at": None,
            "requires_admin": True,
        }

    snapshot_errors = _snapshot_mismatches(plan)
    if snapshot_errors:
        return {
            "ok":         False,
            "plan_id":    plan_id,
            "succeeded":  0,
            "failed":     len(snapshot_errors),
            "errors":     snapshot_errors,
            "executed_at": None,
            "snapshot_changed": True,
        }

    for action in plan.actions:
        try:
            if action.value_name is not None:
                _delete_registry_value(action.hive, action.key_path, action.value_name)
            else:
                _delete_registry_key(action.hive, action.key_path)
            succeeded += 1
        except Exception as exc:
            failed += 1
            errors.append(_format_delete_error(action, exc))

    now = datetime.now(timezone.utc).isoformat()
    if failed == 0:
        update_plan_status(plan_id, "executed", now)
        audit_time = datetime.now()
        insert_clean_records([
            _registry_audit_record(
                action=action,
                plan=plan,
                operation_type="registry_execute",
                timestamp=audit_time,
            )
            for action in plan.actions
        ])

    return {
        "ok":         failed == 0,
        "plan_id":    plan_id,
        "succeeded":  succeeded,
        "failed":     failed,
        "errors":     errors,
        "executed_at": now,
    }


def restore_registry_plan(plan_id: str, confirm_overwrite: bool = False) -> dict:
    """
    Re-import .reg backup files for the given plan via reg.exe import.
    Updates plan status to 'restored'.
    """
    plan = load_plan(plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")

    preview = _restore_preview(plan)
    if preview["requires_confirmation"] and not confirm_overwrite:
        return {
            **preview,
            "ok": False,
            "requires_restore_confirmation": True,
            "succeeded": 0,
            "failed": preview["overwrite_count"] + preview["missing_backup_count"],
            "errors": ["Restore would write registry backup data over the current registry state"],
            "restored_at": None,
        }

    plan_dir  = Path(plan.plan_dir)
    succeeded = 0
    failed    = 0
    errors: list[str] = []
    restored_actions: list[RegistryCleanupAction] = []

    for action in plan.actions:
        reg_path = plan_dir / action.reg_file
        if not reg_path.exists():
            failed += 1
            errors.append(f"{action.reg_file}: backup file not found")
            continue
        result = subprocess.run(
            ["reg.exe", "import", str(reg_path)],
            capture_output=True,
        )
        if result.returncode == 0:
            succeeded += 1
            restored_actions.append(action)
        else:
            failed += 1
            errors.append(f"{action.reg_file}: reg.exe returned code {result.returncode}")

    now = datetime.now(timezone.utc).isoformat()
    update_plan_status(plan_id, "restored", now)
    if succeeded > 0:
        audit_time = datetime.now()
        insert_clean_records([
            _registry_audit_record(
                action=action,
                plan=plan,
                operation_type="registry_restore",
                timestamp=audit_time,
            )
            for action in restored_actions
        ])

    return {
        "ok":          True,
        "plan_id":     plan_id,
        "succeeded":   succeeded,
        "failed":      failed,
        "errors":      errors,
        "restored_at": now,
    }


def list_registry_plans() -> list[dict]:
    from core.storage.registry_cleanup_repository import list_plans
    return list_plans()


def get_registry_plan_detail(plan_id: str) -> dict:
    plan = load_plan(plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")
    meta = _load_plan_meta(plan)
    meta_by_action_id = {
        action.get("id"): action
        for action in meta.get("actions", [])
        if action.get("id")
    }
    return {
        "ok": True,
        "plan": {
            "plan_id": plan.plan_id,
            "created_at": plan.created_at,
            "executed_at": plan.executed_at,
            "restored_at": plan.restored_at,
            "risk_summary": plan.risk_summary,
            "status": plan.status,
            "plan_dir": plan.plan_dir,
            "action_count": len(plan.actions),
            "actions": [
                {
                    "id": action.id,
                    "hive": action.hive,
                    "key_path": action.key_path,
                    "value_name": action.value_name,
                    "category": action.category,
                    "risk": action.risk,
                    "is_system_critical": action.is_system_critical,
                    "reg_file": action.reg_file,
                    "backup_path": str(Path(plan.plan_dir) / action.reg_file),
                    "confidence": meta_by_action_id.get(action.id, {}).get("confidence"),
                    "validation_status": meta_by_action_id.get(action.id, {}).get("validationStatus"),
                    "skip_reason": meta_by_action_id.get(action.id, {}).get("skipReason"),
                }
                for action in plan.actions
            ],
        },
    }


def get_registry_restore_preview(plan_id: str) -> dict:
    plan = load_plan(plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")
    return _restore_preview(plan)
