from dataclasses import dataclass
from typing import Any

from core.models import ScanItem
from core.scanners import SCANNERS


@dataclass
class ScanResult:
    items: list[ScanItem]
    errors: list[dict]
    scanner_reports: list[dict]


class ScannerOrchestrator:
    def run_scan(self) -> ScanResult:
        all_items: list[ScanItem] = []
        errors: list[dict[str, Any]] = []
        scanner_reports: list[dict[str, Any]] = []

        for scanner in SCANNERS:
            try:
                items = scanner.run() or []
                all_items.extend(items)
                scanner_reports.append(build_scanner_report(scanner, items))
            except Exception as error:
                errors.append(build_scanner_error(scanner, error))
                scanner_reports.append(build_scanner_error_report(scanner, error))

        return ScanResult(items=all_items, errors=errors, scanner_reports=scanner_reports)


def build_scanner_report(scanner, items: list[ScanItem]) -> dict[str, Any]:
    return {
        "scanner": scanner.name,
        "category": scanner.category,
        "status": "ok",
        "count": len(items),
        "roots": get_scanner_roots(scanner),
    }


def build_scanner_error(scanner, error: Exception) -> dict[str, Any]:
    return {
        "scanner": scanner.name,
        "error": str(error),
    }


def build_scanner_error_report(scanner, error: Exception) -> dict[str, Any]:
    return {
        "scanner": scanner.name,
        "category": scanner.category,
        "status": "error",
        "count": 0,
        "roots": get_scanner_roots(scanner),
        "error": str(error),
    }


def get_scanner_roots(scanner) -> list[str]:
    if not hasattr(scanner, "get_scan_roots"):
        return []

    try:
        return [str(root) for root in scanner.get_scan_roots()]
    except Exception:
        return []
