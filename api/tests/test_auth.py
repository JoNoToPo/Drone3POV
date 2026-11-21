from datetime import timedelta

import jwt
from sqlalchemy import select

from app.db import User, utcnow
from app.security import COOKIE_NAME

from .conftest import CLIENT_ORIGIN, login

REGISTER = "/api/v1/auth/register"
ME = "/api/v1/users/me"


def test_demo_accounts_exist_with_hashed_passwords(client):
    with client.app.state.SessionLocal() as db:
        users = {u.email: u for u in db.scalars(select(User))}
    assert users["john@john.com"].role == "user"
    assert users["admin@admin.com"].role == "admin"
    for u in users.values():
        assert u.password_hash.startswith("$2")  # bcrypt
        assert u.password_hash not in ("123", "111")


def test_register_then_login(client):
    r = client.post(REGISTER, json={"email": "Tom@Example.com", "password": "secret"})
    assert r.status_code == 201
    assert r.json() == {"id": r.json()["id"], "email": "tom@example.com", "role": "user"}
    assert login(client, "tom@example.com", "secret").status_code == 200


def test_register_cannot_choose_role(client):
    r = client.post(REGISTER, json={"email": "evil@example.com", "password": "secret", "role": "admin"})
    assert r.status_code == 422


def test_duplicate_email_is_409(client):
    client.post(REGISTER, json={"email": "tom@example.com", "password": "secret"})
    r = client.post(REGISTER, json={"email": "TOM@example.com", "password": "other"})
    assert r.status_code == 409


def test_register_validates_input(client):
    assert client.post(REGISTER, json={"email": "not-an-email", "password": "secret"}).status_code == 422
    assert client.post(REGISTER, json={"email": "a@b.co", "password": "x"}).status_code == 422
    assert client.post(REGISTER, json={"email": "a@b.co", "password": "x" * 73}).status_code == 422


def test_wrong_password_is_401_with_same_message_as_unknown_email(client):
    wrong = login(client, "john@john.com", "nope")
    unknown = login(client, "nobody@john.com", "123")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_login_sets_httponly_cookie(client):
    r = login(client, "john@john.com", "123")
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in cookie
    assert "Max-Age=3600" in cookie


def test_production_cookie_is_secure_and_cross_site(make_client):
    c = make_client(cookie_secure=True, cookie_samesite="none")
    cookie = login(c, "john@john.com", "123").headers["set-cookie"].lower()
    assert "secure" in cookie and "samesite=none" in cookie and "httponly" in cookie


def test_me_needs_login(client):
    assert client.get(ME).status_code == 401


def test_me_shows_email_and_role(user_client):
    body = user_client.get(ME).json()
    assert body["email"] == "john@john.com"
    assert body["role"] == "user"


def test_logout_clears_cookie(user_client):
    assert user_client.post("/api/v1/auth/logout").status_code == 200
    assert user_client.get(ME).status_code == 401


def test_expired_token_is_rejected(client, settings):
    payload = {"sub": "1", "role": "user", "iat": utcnow() - timedelta(hours=2), "exp": utcnow() - timedelta(hours=1)}
    expired = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    r = client.get(ME, headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
    assert "expired" in r.json()["detail"]


def test_forged_token_is_rejected(client):
    forged = jwt.encode({"sub": "2", "role": "admin", "exp": utcnow() + timedelta(hours=1)}, "wrong-secret-xxxxxxxxxxxxxxxxxxxxxx", algorithm="HS256")
    assert client.get(ME, headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_bearer_token_works_for_api_clients(client):
    token = login(client, "john@john.com", "123").cookies[COOKIE_NAME]
    client.cookies.clear()
    assert client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_admin_endpoints_need_admin_role(user_client):
    assert user_client.get("/api/v1/admin/users").status_code == 403
    assert user_client.get("/api/v1/admin/stats/endpoints").status_code == 403


def test_admin_sees_users_without_password_hashes(admin_client):
    r = admin_client.get("/api/v1/admin/users")
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()]
    assert {"john@john.com", "admin@admin.com"} <= set(emails)
    assert all("password" not in key for u in r.json() for key in u)


def test_cors_allows_the_client_origin_with_credentials(client):
    r = client.options(ME, headers={"Origin": CLIENT_ORIGIN, "Access-Control-Request-Method": "GET"})
    assert r.headers["access-control-allow-origin"] == CLIENT_ORIGIN
    assert r.headers["access-control-allow-credentials"] == "true"


def test_cors_refuses_other_origins(client):
    r = client.options(ME, headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers


def test_docs_are_served_at_doc(client):
    assert client.get("/doc/").status_code == 200
    spec = client.get("/api/v1/openapi.json").json()
    assert spec["info"]["version"] == "1.0.0"
    assert "/api/v1/vision/detect" in spec["paths"]


def test_host_refuses_dev_secret_and_sqlite(monkeypatch, settings):
    import pytest
    from dataclasses import replace

    from app.config import DEV_JWT_SECRET
    from app.main import check_production_settings

    monkeypatch.setenv("VERCEL", "1")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        check_production_settings(replace(settings, jwt_secret=DEV_JWT_SECRET, database_url="postgresql+psycopg://x/y"))
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        check_production_settings(settings)  # long secret but SQLite
    check_production_settings(replace(settings, database_url="postgresql+psycopg://x/y"))  # fine
