from typing import Any

from core.registry_models import RegistryIssueItem, RegistryScannerReport
from core.services.registry_cleanup_service import get_registry_capabilities
from core.services.registry_scan_service import build_registry_stats, scan_registry
from core.storage.registry_scan_repository import (
    clear_registry_scan_results,
    load_registry_scan_reports,
    load_registry_scan_results,
    save_registry_scan_results,
)


def serialize_registry_issues(items: list[RegistryIssueItem]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in items]


def serialize_registry_reports(reports: list[RegistryScannerReport]) -> list[dict[str, Any]]:
    return [report.model_dump(mode="json") for report in reports]


def build_registry_results_response(
    issues: list[RegistryIssueItem],
    reports: list[RegistryScannerReport],
) -> dict[str, Any]:
    return {
        "ok": True,
        "issues": serialize_registry_issues(issues),
        "stats": build_registry_stats(issues),
        "reports": serialize_registry_reports(reports),
        "count": len(issues),
    }


def execute_registry_scan(scope: str = "Standard", mode: str = "Safe") -> dict[str, Any]:
    result = scan_registry(scope=scope, mode=mode)
    issues = result["issues"]
    reports = result["reports"]
    save_registry_scan_results(issues, reports)
    return build_registry_results_response(issues, reports)


def get_saved_registry_results() -> dict[str, Any]:
    return build_registry_results_response(
        load_registry_scan_results(),
        load_registry_scan_reports(),
    )


def clear_saved_registry_results() -> dict[str, Any]:
    clear_registry_scan_results()
    return {
        "ok": True,
        "cleared": "registry_scan_results",
    }


def get_registry_runtime_capabilities() -> dict[str, Any]:
    return {"ok": True, **get_registry_capabilities()}
