import pytest
from fastapi.testclient import TestClient
from figprism.config import get_settings
from figprism.main import app, limits


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FIGPRISM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FIGPRISM_CONFIG", str(tmp_path / "absent.yaml"))
    monkeypatch.setenv("FIGPRISM_SECRET_KEY", "test-secret-" * 5)
    get_settings.cache_clear()
    limits.clear()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
