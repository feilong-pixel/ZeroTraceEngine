from dataclasses import dataclass

from core.models import ScanItem
from core.scanners import SCANNERS


@dataclass
class ScanResult:
    items: list[ScanItem]
    errors: list[dict]
    scanner_reports: list[dict]


class ScannerOrchestrator:
    def run_scan(self) -> ScanResult:
        all_items = []
        errors = []
        scanner_reports = []

        for scanner in SCANNERS:
            try:
                items = scanner.run()
                all_items.extend(items)
                scanner_reports.append({
                    "scanner": scanner.name,
                    "category": scanner.category,
                    "status": "ok",
                    "count": len(items),
                    "roots": get_scanner_roots(scanner),
                })
            except Exception as error:
                errors.append({"scanner": scanner.name, "error": str(error)})
                scanner_reports.append({
                    "scanner": scanner.name,
                    "category": scanner.category,
                    "status": "error",
                    "count": 0,
                    "roots": get_scanner_roots(scanner),
                    "error": str(error),
                })

        return ScanResult(items=all_items, errors=errors, scanner_reports=scanner_reports)


def get_scanner_roots(scanner) -> list[str]:
    if not hasattr(scanner, "get_scan_roots"):
        return []

    try:
        return [str(root) for root in scanner.get_scan_roots()]
    except Exception:
        return []
