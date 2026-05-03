from pathlib import Path
from typing import List
from datetime import datetime
from core.utils.models import ScanItem

# BaseScanner defines the interface and common properties for all scanners in the system. 
# Each specific scanner (e.g., TempScanner) will inherit from this base class and implement 
# the scan method to perform its specific scanning logic.
class BaseScanner:
    # 扫描器元信息
    name: str = "BaseScanner"
    category: str = "general"     # temp / log / cache / duplicate / update / residue
    risk_level: str = "low"       # default risk
    description: str = "Base scanner"
    version: str = "1.0"

    # 扫描器配置（未来可扩展）
    enabled: bool = True          # 可禁用扫描器
    config: dict = {}             # 扫描器自定义配置

    def scan(self) -> List[ScanItem]:
        """执行扫描，返回 ScanItem 列表"""
        raise NotImplementedError

    def prepare(self):
        """扫描前准备（可选）"""
        pass

    def finalize(self):
        """扫描后清理（可选）"""
        pass

    def get_stats(self, items: List[ScanItem]):
        """返回扫描统计信息"""
        return {
            "scanner": self.name,
            "count": len(items),
            "category": self.category,
            "risk_level": self.risk_level,
            "timestamp": datetime.now().isoformat()
        }
