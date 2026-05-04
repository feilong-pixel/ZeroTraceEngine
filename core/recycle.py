"""Compatibility exports for legacy imports.

New code should import recycle workflows from core.services.recycle_service.
"""

from core.services.recycle_service import (
    is_safe_restore_path,
    list_audit_records,
    list_recycle_records,
    purge_record,
    purge_records,
    restore_record,
    restore_records,
)

__all__ = [
    "is_safe_restore_path",
    "list_audit_records",
    "list_recycle_records",
    "purge_record",
    "purge_records",
    "restore_record",
    "restore_records",
]
