import pytest
import shutil
import uuid
from pathlib import Path

from core.storage import database


@pytest.fixture
def repo_tmp_path():
    path = Path.cwd() / ".test-tmp" / uuid.uuid4().hex
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def isolated_db(repo_tmp_path, monkeypatch):
    db_path = repo_tmp_path / "zerotrace.db"
    monkeypatch.setattr(database, "DATA_DIR", repo_tmp_path)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    return db_path
