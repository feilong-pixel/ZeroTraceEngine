from core.scanners import SCANNERS

class ScannerOrchestrator:
    def run_scan(self):
        all_items = []

        for scanner in SCANNERS:
            scanner.prepare()
            items = scanner.scan()
            scanner.finalize()
            all_items.extend(items)

        return all_items
