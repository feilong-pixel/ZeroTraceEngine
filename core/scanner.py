"""Compatibility exports for legacy imports.

New code should import scanner orchestration from core.services.scanner_service.
"""

from core.services.scanner_service import ScanResult, ScannerOrchestrator

__all__ = ["ScanResult", "ScannerOrchestrator"]
