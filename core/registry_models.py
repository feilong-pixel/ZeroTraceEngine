from typing import Optional
from pydantic import BaseModel


class RegistryIssueItem(BaseModel):
    id: str
    category: str           # InvalidPath / OrphanCOM / InvalidUninstall / InvalidService / StartupIssue / FileAssociation
    risk: str               # Safe / Medium / High
    source: str             # Startup / Uninstall / COM / Service / FileAssociation
    hive: str               # HKCU / HKLM / HKCR
    key_path: str
    value_name: Optional[str] = None
    value_data: Optional[str] = None
    target_path: Optional[str] = None
    description: str
    rule_id: str
    confidence: str = "High"      # High / Medium / Low
    validation_status: str = "missing_target"
    skip_reason: Optional[str] = None
    is_system_critical: bool = False
    selected: bool = True
    ignored: bool = False


class RegistryScannerReport(BaseModel):
    hive: str
    key_path: str
    scan_type: str
    status: str                  # ok / skipped / error
    checked: int = 0
    issues: int = 0
    skipped: int = 0
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    limit: Optional[int] = None
    truncated: bool = False


class RegistryCleanupAction(BaseModel):
    id: str
    plan_id: str
    hive: str
    key_path: str
    value_name: Optional[str] = None
    category: str
    risk: str
    is_system_critical: bool = False
    reg_file: str           # filename inside plan_dir


class RegistryCleanupPlan(BaseModel):
    plan_id: str
    created_at: str
    risk_summary: dict      # {"Safe": n, "Medium": n, "High": n}
    status: str = "pending" # pending / executed / restored
    plan_dir: str
    executed_at: Optional[str] = None
    restored_at: Optional[str] = None
    actions: list[RegistryCleanupAction] = []
