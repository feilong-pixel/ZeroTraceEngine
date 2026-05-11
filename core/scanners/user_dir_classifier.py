"""
UserDirectoryClassifier — maps a file/directory path under %USERPROFILE% to a
UserDirCategory using a priority-ordered rule set.

Priority (highest to lowest):
  1. Directory-name rules  (AI / Python / IDE / System cache)
  2. Extension rules        (log files)
  3. Path-prefix rules      (user data folders)
  4. Large-file rule        (OTHER_LARGE_FILES)
  5. Default fallback
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class UserDirCategory(str, Enum):
    AI_TOOL_CACHE    = "AI_TOOL_CACHE"
    PYTHON_SCI_CACHE = "PYTHON_SCI_CACHE"
    IDE_BUILD_CACHE  = "IDE_BUILD_CACHE"
    SYSTEM_TOOL_CACHE = "SYSTEM_TOOL_CACHE"
    USER_DATA        = "USER_DATA"
    LOG_FILES        = "LOG_FILES"
    OTHER_LARGE_FILES = "OTHER_LARGE_FILES"


# --- rule tables -----------------------------------------------------------

_AI_DIRS: frozenset[str] = frozenset({
    ".claude", ".codex", ".copilot", ".cline", ".continue",
})

_PYTHON_DIRS: frozenset[str] = frozenset({
    ".anaconda", ".conda", ".virtualenvs", ".ipython", ".jupyter",
    ".matplotlib", ".keras", "scikit_learn_data",
})

_IDE_DIRS: frozenset[str] = frozenset({
    ".gradle", ".m2", ".eclipse", ".sts4", ".pydev", ".pleiades",
})
_IDE_PREFIXES: tuple[str, ...] = (".tabnine",)

_SYSTEM_DIRS: frozenset[str] = frozenset({
    ".cache", ".config", ".dotnet", ".Origin", ".QtWebEngineProcess",
    ".sfdx", ".sf",
})

_USER_DATA_ROOTS: tuple[str, ...] = (
    "Desktop", "Documents", "Downloads", "Videos", "Saved Games", "Searches",
)

_LOG_EXTENSIONS: frozenset[str] = frozenset({".log", ".trace"})


class UserDirectoryClassifier:
    def __init__(self, large_file_threshold_bytes: int = 100 * 1024 * 1024) -> None:
        self.large_file_threshold = large_file_threshold_bytes

    def classify(
        self,
        *,
        path: Path,
        root: Path,
        is_dir: bool,
        size_bytes: int,
    ) -> UserDirCategory:
        name = path.name
        rel = path.relative_to(root)
        rel_parts = rel.parts  # e.g. ("Documents", "report.docx")

        # 1. Directory-name rules
        if is_dir:
            name_lower = name.lower()
            if name in _AI_DIRS:
                return UserDirCategory.AI_TOOL_CACHE
            if name in _PYTHON_DIRS:
                return UserDirCategory.PYTHON_SCI_CACHE
            if name in _IDE_DIRS or any(name_lower.startswith(p) for p in _IDE_PREFIXES):
                return UserDirCategory.IDE_BUILD_CACHE
            if name in _SYSTEM_DIRS:
                return UserDirCategory.SYSTEM_TOOL_CACHE

        # 2. Path-prefix rules (user data roots — apply to both files and dirs)
        if rel_parts and rel_parts[0] in _USER_DATA_ROOTS:
            return UserDirCategory.USER_DATA

        # 3. Extension rules
        if not is_dir:
            if path.suffix.lower() in _LOG_EXTENSIONS:
                return UserDirCategory.LOG_FILES

        # 4. Large-file rule (files only)
        if not is_dir and size_bytes >= self.large_file_threshold:
            return UserDirCategory.OTHER_LARGE_FILES

        # 5. Default fallback
        return UserDirCategory.USER_DATA if not is_dir else UserDirCategory.SYSTEM_TOOL_CACHE
