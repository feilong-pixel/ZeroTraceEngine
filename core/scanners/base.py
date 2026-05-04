from pathlib import Path
from typing import List
from datetime import datetime
from core.models import ScanItem
from dataclasses import dataclass, field

# BaseScanner defines the interface and common properties for all scanners in the system. 
# Each specific scanner (e.g., TempScanner) will inherit from this base class and implement 
# the scan method to perform its specific scanning logic.
@dataclass
class BaseScanner:
    # Scanner metadata.
    name: str = "BaseScanner"
    category: str = "general"     # temp / log / cache / duplicate / update / residue
    risk_level: str = "low"       # default risk
    description: str = "Base scanner"
    version: str = "1.0"

    # Scanner configuration.
    enabled: bool = True

    # Avoid sharing one mutable config dict across scanner instances.
    config: dict = field(default_factory=dict)

    def scan(self) -> list[ScanItem]:
        """Run the scan and return discovered ScanItem records."""
        raise NotImplementedError

    def prepare(self) -> None:
        """Optional preparation before scanning."""
        pass

    def finalize(self) -> None:
        """Optional cleanup after scanning."""
        pass

    def run(self) -> list[ScanItem]:
        """Run the scanner lifecycle in a fixed prepare/scan/finalize order."""
        self.prepare()
        try:
            self._results = self.scan()
            return self._results
        finally:
            self.finalize()

    def get_stats(self) -> dict:
        """Return basic scanner statistics."""
        return {
            "scanner": self.name,
            "count": len(self._results) if hasattr(self, '_results') else 0,
            "category": self.category,
            "risk_level": self.risk_level,
            "timestamp": datetime.now().isoformat()
        }
