from core.scanners import SCANNERS

class ScannerOrchestrator:
    def run_scan(self):
        all_items = []

        for scanner in SCANNERS:
            try:
                scanner.prepare()
                items = scanner.scan()
            except Exception:
                continue
            finally:
                try:
                    scanner.finalize()
                except Exception:
                    pass

            all_items.extend(items)

        return all_items
