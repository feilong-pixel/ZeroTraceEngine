# core/config.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

class AppConfig:
    db_path: Path = BASE_DIR / "data" / "zerotrace.db"
    recycle_root: Path = BASE_DIR / "ZeroTraceRecycle"
    scan_max_depth: int = 5
    temp_dirs: list[Path] = [
        Path("C:/Windows/Temp"),
        Path.home() / "AppData/Local/Temp",
    ]

settings = AppConfig()
