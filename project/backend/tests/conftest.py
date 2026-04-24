import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_supabase


@pytest.fixture
def mock_supabase():
    return MagicMock()


@pytest.fixture
def client(mock_supabase):
    app.dependency_overrides[get_supabase] = lambda: mock_supabase
    yield TestClient(app)
    app.dependency_overrides.clear()
