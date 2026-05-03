from pathlib import Path
import uuid
from datetime import datetime

RECYCLE_ROOT = Path("ZeroTraceRecycle")

def generate_recycle_path(original_path: str, unique_id: str | None = None) -> Path:
    """
    生成 ZeroTrace Engine 的回收站路径：
    ZeroTraceRecycle/YYYYMMDD/uuid/originalname.ext
    """
    # 1. 根目录
    RECYCLE_ROOT.mkdir(parents=True, exist_ok=True)

    # 2. 日期目录
    date_dir = RECYCLE_ROOT / datetime.now().strftime("%Y%m%d")
    date_dir.mkdir(parents=True, exist_ok=True)

    # 3. UUID 目录
    recycle_id = unique_id or uuid.uuid4().hex
    uuid_dir = date_dir / recycle_id
    uuid_dir.mkdir(parents=True, exist_ok=True)

    # 4. 原文件名
    original_name = Path(original_path).name

    # 5. 最终路径
    return uuid_dir / original_name
