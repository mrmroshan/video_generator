import os
import sys
import pytest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Isolated SQLite DB for each test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("MOCK_APIS", "true")
    import importlib
    import data.db as db
    importlib.reload(db)
    db.init_db()
    return db


@pytest.fixture
def mock_job():
    """Minimal 5-scene job dict for testing."""
    from orchestration.crew import _mock_blueprint
    return _mock_blueprint("test topic", "youtube")


@pytest.fixture
def client(tmp_db):
    """FastAPI test client with isolated DB."""
    import importlib
    import dashboard.server as srv
    importlib.reload(srv)
    from fastapi.testclient import TestClient
    return TestClient(srv.app)
