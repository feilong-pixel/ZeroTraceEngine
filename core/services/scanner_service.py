from dataclasses import dataclass

from core.models import ScanItem
from core.scanners import SCANNERS


@dataclass
class ScanResult:
    items: list[ScanItem]
    errors: list[dict]


class ScannerOrchestrator:
    def run_scan(self) -> ScanResult:
        all_items = []
        errors = []

        for scanner in SCANNERS:
            try:
                items = scanner.run()
                all_items.extend(items)
            except Exception as error:
                errors.append({"scanner": scanner.name, "error": str(error)})

        return ScanResult(items=all_items, errors=errors)
