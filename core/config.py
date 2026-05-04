# core/config.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

class AppConfig:
    db_path: Path = BASE_DIR / "data" / "zerotrace.db"
    recycle_root: Path = BASE_DIR / "ZeroTraceRecycle"
    scan_max_depth: int = 5
    temp_file_min_age_hours: int = 24
    browser_cache_min_age_hours: int = 24
    log_file_min_age_days: int = 7
    temp_dirs: list[Path] = [
        Path("C:/Windows/Temp"),
        Path.home() / "AppData/Local/Temp",
    ]
    browser_cache_dirs: list[Path] = [
        Path("C:/Users") / Path.home().name / "AppData/Local/Google/Chrome/User Data/Default/Cache",
        Path("C:/Users") / Path.home().name / "AppData/Local/Microsoft/Edge/User Data/Default/Cache",
    ]
    log_dirs: list[Path] = [
        BASE_DIR / "logs",
        Path("C:/Log"),
    ]

settings = AppConfig()
