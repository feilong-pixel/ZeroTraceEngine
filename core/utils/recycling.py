from pathlib import Path
import uuid
from datetime import datetime
from core.config import settings

def generate_recycle_path(original_path: str, unique_id: str | None = None) -> Path:
    """
    Generate a ZeroTrace Engine recycle path:
    ZeroTraceRecycle/YYYYMMDD/uuid/originalname.ext
    """
    # Root directory.
    settings.recycle_root.mkdir(parents=True, exist_ok=True)

    # Date directory.
    date_dir = settings.recycle_root / datetime.now().strftime("%Y%m%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    # UUID directory.
    recycle_id = unique_id or uuid.uuid4().hex
    uuid_dir = date_dir / recycle_id
    uuid_dir.mkdir(parents=True, exist_ok=True)

    # Original filename.
    original_name = Path(original_path).name

    # Final recycle path.
    return uuid_dir / original_name
