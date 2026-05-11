from typing import Optional
from pydantic import BaseModel, Field


class AppScanItem(BaseModel):
    id: str
    name: str
    version: Optional[str] = None
    publisher: Optional[str] = None
    install_path: Optional[str] = None
    size_bytes: Optional[int] = None
    source: str                        # "registry" | "directory" | "uwp"
    last_modified: Optional[str] = None
    is_valid: bool = True
    is_portable: bool = False
    notes: list[str] = Field(default_factory=list)
    residual_reason: Optional[str] = None


class AppScanSummary(BaseModel):
    total_apps: int = 0
    total_size_bytes: int = 0
    invalid_count: int = 0
    by_source: dict[str, int] = Field(default_factory=dict)
    largest_app_name: Optional[str] = None
    largest_app_bytes: Optional[int] = None
    scanned_registry_keys: int = 0
    scanned_directories: int = 0


class AppScanMeta(BaseModel):
    scan_id: int
    started_at: str
    finished_at: str
    duration_ms: int
    total_apps: int
    invalid_count: int
