from datetime import datetime
from pydantic import BaseModel

# ScanItem represents a single item found during scanning, with details about its path, size, type, and risk level
class ScanItem(BaseModel):
    path: str
    size: int
    mtime: datetime | None = None

    # file / folder / registry / cache / thumbnail / duplicate
    file_type: str = "file" 

    # temp / log / cache / duplicate / update / residue
    category: str

    # Chrome / Edge / Windows Update / AppName
    source: str

    # TempScanner / BrowserCacheScanner
    scanner: str

    # low / medium / high
    risk_level: str = "low"

    # SHA-256
    hash: str | None = None


# CleanRecord extends ScanItem with additional fields for tracking the cleaning process
class CleanRecord(BaseModel):
    id: str
    unique_id: str
    original_path: str
    recycle_path: str
    size: int

    # file / folder / cache / thumbnail / duplicate
    file_type: str = "file"

    category: str
    source: str
    scanner: str
    risk_level: str = "low"

    hash: str | None = None

    operation_type: str = "move_to_recycle"
    deleted_at: datetime
    restored_at: datetime | None = None
    purged_at: datetime | None = None

