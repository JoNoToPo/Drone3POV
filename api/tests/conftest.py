from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.drone import SimulatedDrone
from app.main import create_app

CLIENT_ORIGIN = "http://client.test"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings(tmp_path) -> Settings:
    # TestClient talks plain HTTP, so the cookie can't be Secure here. Production keeps Secure + SameSite=None.
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        jwt_secret="test-secret-that-is-long-enough-for-hs256",
        cookie_secure=False,
        cookie_samesite="lax",
        client_origins=(CLIENT_ORIGIN,),
    )


@pytest.fixture
def make_client(settings):
    def _make(**overrides) -> TestClient:
        return TestClient(create_app(replace(settings, **overrides), drone=SimulatedDrone()))
    return _make


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def login(client: TestClient, email: str, password: str):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


@pytest.fixture
def user_client(client) -> TestClient:
    assert login(client, "john@john.com", "123").status_code == 200
    return client


@pytest.fixture
def admin_client(make_client) -> TestClient:
    c = make_client()
    assert login(c, "admin@admin.com", "111").status_code == 200
    return c
