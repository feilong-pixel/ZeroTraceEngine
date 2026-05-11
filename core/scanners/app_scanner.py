"""
AppScanner — identifies installed applications from registry and common directories.

Phases:
  1. RegistryAppLocator   : read HKLM/HKCU/WOW6432Node Uninstall keys
  2. DirectoryAppLocator  : heuristic scan of common install paths
  3. AppInstallLocator    : merge & deduplicate by normalized install path
  4. DirectorySizeAnalyzer: parallel directory size computation
  5. Aggregation          : build summary
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import winreg
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from core.app_scan_models import AppScanItem, AppScanSummary

# ---------------------------------------------------------------------------
# Registry roots
# ---------------------------------------------------------------------------

_UNINSTALL_ROOTS = [
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall",         "HKLM"),
    (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Uninstall",         "HKCU"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM-WOW"),
]

# Common install root paths
_INSTALL_ROOTS = [
    Path(r"C:\Program Files"),
    Path(r"C:\Program Files (x86)"),
    Path(r"C:\ProgramData"),
]
_LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local"))
_APPDATA      = Path(os.environ.get("APPDATA",      r"C:\Users\Default\AppData\Roaming"))

# Directories that are app containers — scan sub-dirs, not them directly
_PROGRAMS_SUBDIRS = frozenset({
    Path(r"C:\Program Files"),
    Path(r"C:\Program Files (x86)"),
})

# Sub-paths within LOCALAPPDATA / APPDATA that commonly hold installed apps
_LOCALAPPDATA_SUBROOTS = ["Programs"]
_APPDATA_SUBROOTS: list[str] = []

_MIN_DIR_BYTES = 10 * 1024 * 1024   # 10 MB
_APP_EXTENSIONS = frozenset({".exe", ".dll", ".pak", ".bin"})
_SKIP_DIR_NAMES = frozenset({
    "temp", "tmp", "cache", "logs", "log", "roaming",
    "microsoft", "windows", "$recycle.bin", "windowsapps",
    "packages",
})

_MAX_CONCURRENCY = 6
_MAX_SIZE_SCAN_SECONDS = 8.0
_MIN_SIZE_SCAN_SECONDS = 2.0
_MAX_ALLOWED_SIZE_SCAN_SECONDS = 60.0
_SIZE_SCAN_TIME_CHECK_INTERVAL = 128


def _make_id(*parts: str) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()


def _read_reg_value(key, name: str) -> Optional[str]:
    try:
        val, _ = winreg.QueryValueEx(key, name)
        return str(val).strip() if val is not None else None
    except (OSError, ValueError):
        return None


def _normalize_path(p: str) -> str:
    return os.path.normcase(os.path.normpath(p.strip()))


def _clean_registry_path(value: str) -> Optional[str]:
    text = value.strip().strip('"')
    if not text:
        return None
    if "," in text:
        candidate, suffix = text.rsplit(",", 1)
        if suffix.strip().lstrip("-").isdigit():
            text = candidate.strip().strip('"')
    return os.path.expandvars(text) or None


def _path_from_registry_command(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    text = os.path.expandvars(value.strip())
    quoted = re.search(r'"([^"]+\.(?:exe|msi|bat|cmd))"', text, re.IGNORECASE)
    if quoted:
        return str(Path(quoted.group(1)).parent)

    unquoted = re.search(r"([A-Za-z]:\\[^\s\"']+\.(?:exe|msi|bat|cmd))", text, re.IGNORECASE)
    if unquoted:
        return str(Path(unquoted.group(1)).parent)

    return None


def _infer_install_path(
    install_location: Optional[str],
    display_icon: Optional[str],
    uninstall_string: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    if install_location:
        path = _clean_registry_path(install_location)
        if path:
            return path, "InstallLocation"

    icon_path = _clean_registry_path(display_icon or "")
    if icon_path:
        path = Path(icon_path)
        if path.is_file():
            return str(path.parent), "DisplayIcon"
        if path.is_dir():
            return str(path), "DisplayIcon"

    command_path = _path_from_registry_command(uninstall_string)
    if command_path and Path(command_path).exists():
        return command_path, "UninstallString"

    return None, None


# ---------------------------------------------------------------------------
# Phase 1 — RegistryAppLocator
# ---------------------------------------------------------------------------

def _scan_registry_root(hive, key_path: str, hive_label: str) -> tuple[list[AppScanItem], int]:
    items: list[AppScanItem] = []
    checked = 0
    try:
        with winreg.OpenKey(hive, key_path, access=winreg.KEY_READ) as root:
            idx = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, idx)
                    idx += 1
                    checked += 1
                except OSError:
                    break
                item = _read_uninstall_entry(hive, f"{key_path}\\{sub}", hive_label)
                if item:
                    items.append(item)
    except (PermissionError, OSError, FileNotFoundError):
        pass
    return items, checked


def _read_uninstall_entry(hive, subkey_path: str, hive_label: str) -> Optional[AppScanItem]:
    try:
        with winreg.OpenKey(hive, subkey_path, access=winreg.KEY_READ) as key:
            name = _read_reg_value(key, "DisplayName")
            if not name:
                return None
            # Skip Windows system components
            sys_comp = _read_reg_value(key, "SystemComponent")
            if sys_comp == "1":
                return None

            install_path, path_source = _infer_install_path(
                _read_reg_value(key, "InstallLocation"),
                _read_reg_value(key, "DisplayIcon"),
                _read_reg_value(key, "UninstallString"),
            )
            version   = _read_reg_value(key, "DisplayVersion") or None
            publisher = _read_reg_value(key, "Publisher") or None
            est_kb    = _read_reg_value(key, "EstimatedSize")

            size_bytes: Optional[int] = None
            if est_kb:
                try:
                    size_bytes = int(est_kb) * 1024
                except ValueError:
                    pass

            is_valid = True
            notes: list[str] = ["From registry"]
            residual_reason: Optional[str] = None

            if install_path is None:
                notes.append("No install path (registry-only)")
                residual_reason = "registry-only / unknown path"
            elif not Path(install_path).exists():
                is_valid = False
                notes.append("Install path does not exist (residual entry)")
                residual_reason = "目录已删除，注册表残留"
            elif path_source and path_source != "InstallLocation":
                notes.append(f"Install path inferred from {path_source}")

            if size_bytes is not None:
                notes.append("Estimated size from registry")

            return AppScanItem(
                id=_make_id(name, install_path or subkey_path),
                name=name,
                version=version,
                publisher=publisher,
                install_path=install_path,
                size_bytes=size_bytes,
                source="registry",
                is_valid=is_valid,
                is_portable=False,
                notes=notes,
                residual_reason=residual_reason,
            )
    except (PermissionError, OSError, ValueError):
        return None


def collect_registry_apps() -> tuple[list[AppScanItem], int]:
    all_items: list[AppScanItem] = []
    total_checked = 0
    for hive, key_path, label in _UNINSTALL_ROOTS:
        items, checked = _scan_registry_root(hive, key_path, label)
        all_items.extend(items)
        total_checked += checked
    return all_items, total_checked


# ---------------------------------------------------------------------------
# Phase 2 — DirectoryAppLocator
# ---------------------------------------------------------------------------

def _is_app_dir(d: Path) -> bool:
    name_lower = d.name.lower()
    if name_lower in _SKIP_DIR_NAMES:
        return False
    # Check for exe up to depth 2
    try:
        for entry in d.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".exe":
                return True
        for entry in d.iterdir():
            if entry.is_dir():
                try:
                    for sub in entry.iterdir():
                        if sub.is_file() and sub.suffix.lower() == ".exe":
                            return True
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        return False
    # Fallback: check for common app file extensions and approximate size
    try:
        has_app_files = any(
            entry.is_file() and entry.suffix.lower() in _APP_EXTENSIONS
            for entry in d.iterdir()
        )
        return has_app_files
    except (PermissionError, OSError):
        return False


def _scan_dir_root(root: Path) -> list[AppScanItem]:
    items: list[AppScanItem] = []
    if not root.exists():
        return items
    try:
        for child in root.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            if _is_app_dir(child):
                is_portable = root not in _PROGRAMS_SUBDIRS
                items.append(AppScanItem(
                    id=_make_id(child.name, str(child)),
                    name=child.name,
                    version=None,
                    publisher=None,
                    install_path=str(child),
                    size_bytes=None,
                    source="directory",
                    is_valid=True,
                    is_portable=is_portable,
                    notes=["From directory scan"],
                ))
    except (PermissionError, OSError):
        pass
    return items


def collect_directory_apps() -> tuple[list[AppScanItem], int]:
    all_items: list[AppScanItem] = []
    roots: list[Path] = []

    # Standard Program Files roots — scan their children
    for r in _INSTALL_ROOTS:
        roots.append(r)

    # LOCALAPPDATA\Programs and similar
    for sub in _LOCALAPPDATA_SUBROOTS:
        p = _LOCALAPPDATA / sub
        if p.exists():
            roots.append(p)

    dir_count = len(roots)
    for root in roots:
        all_items.extend(_scan_dir_root(root))

    return all_items, dir_count


# ---------------------------------------------------------------------------
# Phase 3 — AppInstallLocator (merge & deduplicate)
# ---------------------------------------------------------------------------

def merge_apps(
    registry_apps: list[AppScanItem],
    directory_apps: list[AppScanItem],
) -> list[AppScanItem]:
    path_map: dict[str, AppScanItem] = {}
    no_path: list[AppScanItem] = []

    for app in registry_apps:
        if app.install_path:
            key = _normalize_path(app.install_path)
            path_map[key] = app
        else:
            no_path.append(app)

    for app in directory_apps:
        if app.install_path:
            key = _normalize_path(app.install_path)
            if key not in path_map:
                path_map[key] = app

    return list(path_map.values()) + no_path


# ---------------------------------------------------------------------------
# Phase 4 — DirectorySizeAnalyzer
# ---------------------------------------------------------------------------

def clamp_size_scan_timeout(seconds: float) -> float:
    return max(_MIN_SIZE_SCAN_SECONDS, min(seconds, _MAX_ALLOWED_SIZE_SCAN_SECONDS))


def _calc_dir_size(path: str, timeout_seconds: Optional[float] = _MAX_SIZE_SCAN_SECONDS) -> tuple[Optional[int], Optional[str], Optional[str]]:
    total = 0
    scanned_files = 0
    deadline = time.monotonic() + clamp_size_scan_timeout(timeout_seconds) if timeout_seconds is not None else None
    latest_mtime: Optional[float] = None
    try:
        for root_str, dirs, files in os.walk(path):
            for f in files:
                scanned_files += 1
                if deadline is not None and scanned_files % _SIZE_SCAN_TIME_CHECK_INTERVAL == 0 and time.monotonic() > deadline:
                    last_mod = None
                    if latest_mtime is not None:
                        last_mod = datetime.fromtimestamp(latest_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
                    return total, last_mod, "Directory size scan timed out; partial size"
                fp = os.path.join(root_str, f)
                try:
                    st = os.stat(fp)
                    total += st.st_size
                    if latest_mtime is None or st.st_mtime > latest_mtime:
                        latest_mtime = st.st_mtime
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        return None, None, "Failed to access directory"

    last_mod: Optional[str] = None
    if latest_mtime is not None:
        last_mod = datetime.fromtimestamp(latest_mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    return total, last_mod, None


def compute_sizes(
    apps: list[AppScanItem],
    max_concurrency: int = _MAX_CONCURRENCY,
    size_scan_timeout_seconds: Optional[float] = _MAX_SIZE_SCAN_SECONDS,
) -> None:
    targets = [a for a in apps if a.is_valid and a.install_path and a.size_bytes is None]
    if not targets:
        return

    with ThreadPoolExecutor(max_workers=max_concurrency) as pool:
        futures = {pool.submit(_calc_dir_size, a.install_path, size_scan_timeout_seconds): a for a in targets}
        for future in as_completed(futures):
            app = futures[future]
            try:
                size, last_mod, warning = future.result()
                if size is not None:
                    app.size_bytes = size
                    app.notes = [n for n in app.notes if n != "Estimated size from registry"]
                    if warning == "Directory size scan timed out; partial size":
                        app.notes.append("Partial size from directory")
                    else:
                        app.notes.append("Size computed from directory")
                if last_mod and not app.last_modified:
                    app.last_modified = last_mod
                if warning:
                    app.notes.append(warning)
            except Exception:
                app.notes.append("Failed to access directory")


# ---------------------------------------------------------------------------
# Phase 5 — Aggregation
# ---------------------------------------------------------------------------

def build_summary(
    apps: list[AppScanItem],
    scanned_registry_keys: int,
    scanned_directories: int,
) -> AppScanSummary:
    total_size = sum(a.size_bytes or 0 for a in apps)
    invalid = [a for a in apps if not a.is_valid]
    valid = [a for a in apps if a.is_valid]

    by_source: dict[str, int] = {"registry": 0, "directory": 0, "uwp": 0}
    for a in apps:
        by_source[a.source] = by_source.get(a.source, 0) + 1

    largest: Optional[AppScanItem] = None
    if valid:
        largest = max(valid, key=lambda a: a.size_bytes or 0, default=None)

    return AppScanSummary(
        total_apps=len(apps),
        total_size_bytes=total_size,
        invalid_count=len(invalid),
        by_source=by_source,
        largest_app_name=largest.name if largest else None,
        largest_app_bytes=largest.size_bytes if largest else None,
        scanned_registry_keys=scanned_registry_keys,
        scanned_directories=scanned_directories,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class AppScanResult:
    apps: list[AppScanItem]
    summary: AppScanSummary
    started_at: str
    finished_at: str
    duration_ms: int


@dataclass
class AppScanDiscovery:
    apps: list[AppScanItem]
    started_at: str
    started_at_dt: datetime
    scanned_registry_keys: int
    scanned_directories: int


ProgressCallback = Callable[[str, dict], None]


def discover_app_scan(
    progress_callback: ProgressCallback | None = None,
) -> AppScanDiscovery:
    def progress(stage: str, **payload) -> None:
        if progress_callback:
            progress_callback(stage, payload)

    t0 = datetime.now(tz=timezone.utc)
    started_at = t0.strftime("%Y-%m-%d %H:%M:%S")

    progress("registry", scanned_registry_keys=0, scanned_directories=0, total_apps=0)
    reg_apps, reg_checked   = collect_registry_apps()
    progress("directory", scanned_registry_keys=reg_checked, scanned_directories=0, total_apps=len(reg_apps))
    dir_apps, dir_count     = collect_directory_apps()
    progress("merge", scanned_registry_keys=reg_checked, scanned_directories=dir_count, total_apps=len(reg_apps) + len(dir_apps))
    merged                  = merge_apps(reg_apps, dir_apps)
    return AppScanDiscovery(
        apps=merged,
        started_at=started_at,
        started_at_dt=t0,
        scanned_registry_keys=reg_checked,
        scanned_directories=dir_count,
    )


def complete_app_scan(
    discovery: AppScanDiscovery,
    max_concurrency: int = _MAX_CONCURRENCY,
    size_scan_timeout_seconds: float = _MAX_SIZE_SCAN_SECONDS,
    progress_callback: ProgressCallback | None = None,
) -> AppScanResult:
    def progress(stage: str, **payload) -> None:
        if progress_callback:
            progress_callback(stage, payload)

    merged = discovery.apps
    reg_checked = discovery.scanned_registry_keys
    dir_count = discovery.scanned_directories
    timeout_seconds = clamp_size_scan_timeout(size_scan_timeout_seconds)
    progress("sizes", scanned_registry_keys=reg_checked, scanned_directories=dir_count, total_apps=len(merged), size_scan_timeout_seconds=timeout_seconds)
    compute_sizes(
        merged,
        max_concurrency=max_concurrency,
        size_scan_timeout_seconds=timeout_seconds,
    )

    t1 = datetime.now(tz=timezone.utc)
    finished_at = t1.strftime("%Y-%m-%d %H:%M:%S")
    duration_ms = int((t1 - discovery.started_at_dt).total_seconds() * 1000)

    summary = build_summary(merged, reg_checked, dir_count)
    progress(
        "aggregate",
        scanned_registry_keys=reg_checked,
        scanned_directories=dir_count,
        total_apps=summary.total_apps,
        invalid_count=summary.invalid_count,
    )

    return AppScanResult(
        apps=merged,
        summary=summary,
        started_at=discovery.started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
    )


def run_app_scan(
    max_concurrency: int = _MAX_CONCURRENCY,
    size_scan_timeout_seconds: float = _MAX_SIZE_SCAN_SECONDS,
    progress_callback: ProgressCallback | None = None,
) -> AppScanResult:
    discovery = discover_app_scan(progress_callback=progress_callback)
    return complete_app_scan(
        discovery,
        max_concurrency=max_concurrency,
        size_scan_timeout_seconds=size_scan_timeout_seconds,
        progress_callback=progress_callback,
    )
