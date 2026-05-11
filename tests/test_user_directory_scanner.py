"""
Tests for UserDirectoryClassifier and UserDirectoryScanner.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.scanners.user_dir_classifier import UserDirCategory, UserDirectoryClassifier
from core.scanners.user_directory_scanner import UserDirectoryScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_classifier(threshold_mb: int = 100) -> UserDirectoryClassifier:
    return UserDirectoryClassifier(large_file_threshold_bytes=threshold_mb * 1024 * 1024)


def classify(root: Path, rel: str, is_dir: bool, size: int = 0, threshold_mb: int = 100) -> UserDirCategory:
    path = root / Path(rel)
    c = make_classifier(threshold_mb)
    return c.classify(path=path, root=root, is_dir=is_dir, size_bytes=size)


# ---------------------------------------------------------------------------
# Classifier — AI tool cache
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [".claude", ".codex", ".copilot", ".cline", ".continue"])
def test_ai_tool_cache_dirs(repo_tmp_path, name):
    assert classify(repo_tmp_path, name, is_dir=True) == UserDirCategory.AI_TOOL_CACHE


# ---------------------------------------------------------------------------
# Classifier — Python / science cache
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    ".anaconda", ".conda", ".virtualenvs", ".ipython",
    ".jupyter", ".matplotlib", ".keras", "scikit_learn_data",
])
def test_python_sci_cache_dirs(repo_tmp_path, name):
    assert classify(repo_tmp_path, name, is_dir=True) == UserDirCategory.PYTHON_SCI_CACHE


# ---------------------------------------------------------------------------
# Classifier — IDE / build cache
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [".gradle", ".m2", ".eclipse", ".sts4", ".pydev", ".pleiades"])
def test_ide_build_cache_dirs(repo_tmp_path, name):
    assert classify(repo_tmp_path, name, is_dir=True) == UserDirCategory.IDE_BUILD_CACHE


def test_tabnine_prefix(repo_tmp_path):
    assert classify(repo_tmp_path, ".tabnine-server-3.5", is_dir=True) == UserDirCategory.IDE_BUILD_CACHE


# ---------------------------------------------------------------------------
# Classifier — system tool cache
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [".cache", ".config", ".dotnet", ".Origin", ".sfdx", ".sf"])
def test_system_tool_cache_dirs(repo_tmp_path, name):
    assert classify(repo_tmp_path, name, is_dir=True) == UserDirCategory.SYSTEM_TOOL_CACHE


# ---------------------------------------------------------------------------
# Classifier — user data path prefixes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel,is_dir", [
    ("Desktop",              True),
    ("Documents",            True),
    ("Downloads",            True),
    ("Videos",               True),
    ("Saved Games",          True),
    ("Searches",             True),
    ("Desktop/report.pdf",   False),
    ("Documents/notes.txt",  False),
    ("Downloads/setup.exe",  False),
])
def test_user_data_paths(repo_tmp_path, rel, is_dir):
    assert classify(repo_tmp_path, rel, is_dir=is_dir) == UserDirCategory.USER_DATA


# ---------------------------------------------------------------------------
# Classifier — log files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", ["error.log", "debug.trace", "app.log"])
def test_log_files(repo_tmp_path, filename):
    assert classify(repo_tmp_path, filename, is_dir=False) == UserDirCategory.LOG_FILES


def test_log_inside_user_data_dir_is_user_data(repo_tmp_path):
    # Path-prefix rule (USER_DATA) beats extension rule (.log) per spec §8
    assert classify(repo_tmp_path, "Downloads/error.log", is_dir=False) == UserDirCategory.USER_DATA


# ---------------------------------------------------------------------------
# Classifier — large files
# ---------------------------------------------------------------------------

def test_large_file_above_threshold(repo_tmp_path):
    size = 150 * 1024 * 1024  # 150 MB
    assert classify(repo_tmp_path, "bigfile.bin", is_dir=False, size=size, threshold_mb=100) == UserDirCategory.OTHER_LARGE_FILES


def test_file_below_threshold_not_large(repo_tmp_path):
    size = 50 * 1024 * 1024  # 50 MB
    result = classify(repo_tmp_path, "smallfile.bin", is_dir=False, size=size, threshold_mb=100)
    assert result != UserDirCategory.OTHER_LARGE_FILES


# ---------------------------------------------------------------------------
# Classifier — fallback rules
# ---------------------------------------------------------------------------

def test_unknown_dir_fallback(repo_tmp_path):
    assert classify(repo_tmp_path, "SomeRandomDir", is_dir=True) == UserDirCategory.SYSTEM_TOOL_CACHE


def test_unknown_file_fallback(repo_tmp_path):
    assert classify(repo_tmp_path, "unknown.xyz", is_dir=False) == UserDirCategory.USER_DATA


# ---------------------------------------------------------------------------
# Classifier — priority: dir-name beats extension
# ---------------------------------------------------------------------------

def test_ai_dir_beats_log_extension(repo_tmp_path):
    assert classify(repo_tmp_path, ".claude", is_dir=True) == UserDirCategory.AI_TOOL_CACHE


# ---------------------------------------------------------------------------
# Scanner smoke test
# ---------------------------------------------------------------------------

def test_scanner_runs_on_temp_root(repo_tmp_path):
    root = repo_tmp_path
    (root / ".claude").mkdir()
    (root / ".conda").mkdir()
    (root / "Downloads").mkdir()
    (root / "Documents").mkdir()
    (root / "error.log").write_text("log content")

    scanner = UserDirectoryScanner(
        root=root,
        large_file_threshold_bytes=100 * 1024 * 1024,
        max_concurrency=2,
    )
    result = scanner.run()

    assert result.root_path == str(root)
    assert result.total_dir_count >= 4
    assert result.total_file_count >= 1

    paths = {item.path for item in result.items}
    assert str(root / ".claude") in paths
    assert str(root / ".conda") in paths
    assert str(root / "Downloads") in paths
    assert str(root / "error.log") in paths


def test_scanner_category_distribution(repo_tmp_path):
    root = repo_tmp_path
    (root / ".claude").mkdir()
    (root / ".jupyter").mkdir()
    (root / ".gradle").mkdir()
    (root / "Downloads").mkdir()
    (root / "app.log").write_text("log")

    scanner = UserDirectoryScanner(root=root, large_file_threshold_bytes=100 * 1024 * 1024)
    result = scanner.run()

    by_category = {item.category: item for item in result.items}
    assert UserDirCategory.AI_TOOL_CACHE.value in by_category
    assert UserDirCategory.PYTHON_SCI_CACHE.value in by_category
    assert UserDirCategory.IDE_BUILD_CACHE.value in by_category
    assert UserDirCategory.USER_DATA.value in by_category
    assert UserDirCategory.LOG_FILES.value in by_category


def test_scanner_summary_totals(repo_tmp_path):
    root = repo_tmp_path
    (root / "Downloads").mkdir()
    (root / "file.txt").write_text("hello")

    scanner = UserDirectoryScanner(root=root)
    result = scanner.run()

    summary_total = sum(s.size_bytes for s in result.summary.values())
    assert summary_total == result.total_size_bytes


def test_scanner_excludes_git(repo_tmp_path):
    root = repo_tmp_path
    (root / ".git").mkdir()
    (root / "node_modules").mkdir()

    scanner = UserDirectoryScanner(root=root)
    result = scanner.run()

    paths = {item.path for item in result.items}
    assert str(root / ".git") not in paths
    assert str(root / "node_modules") not in paths
