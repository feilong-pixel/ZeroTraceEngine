"""Compatibility exports for legacy imports.

New code should use core.services.cleaner_service and core.storage repositories.
"""

from core.services.cleaner_service import (
    execute_cleanup,
    is_recyclable_empty_dir,
    is_under_empty_dir_cleanup_root,
    move_empty_parent_dirs_to_recycle,
    move_to_recycle,
)
from core.storage.clean_log_repository import insert_clean_record
from core.storage.scan_results_repository import discard_scan_result

__all__ = [
    "discard_scan_result",
    "execute_cleanup",
    "insert_clean_record",
    "is_recyclable_empty_dir",
    "is_under_empty_dir_cleanup_root",
    "move_empty_parent_dirs_to_recycle",
    "move_to_recycle",
]
