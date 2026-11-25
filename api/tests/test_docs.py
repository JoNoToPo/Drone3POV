"""The Swagger docs are what markers and the lab use, so check they describe the API correctly."""


def _spec(client):
    return client.get("/api/v1/openapi.json").json()


def test_doc_without_slash_redirects(client):
    r = client.get("/doc", follow_redirects=False)
    assert r.status_code in (301, 302, 307, 308)
    assert r.headers["location"] == "/doc/"


def test_swagger_ui_sends_cookies(client):
    html = client.get("/doc/").text
    assert '"withCredentials": true' in html
    assert '"persistAuthorization": true' in html


def test_auth_schemes_are_documented(client):
    schemes = _spec(client)["components"]["securitySchemes"]
    assert schemes["cookieAuth"] == {
        "type": "apiKey", "in": "cookie", "name": "access_token",
        "description": schemes["cookieAuth"]["description"],
    }
    assert schemes["bearerAuth"]["scheme"] == "bearer"


def test_protected_routes_are_marked_and_public_ones_are_not(client):
    paths = _spec(client)["paths"]
    for path, method in [
        ("/api/v1/users/me", "get"),
        ("/api/v1/vision/detect", "post"),
        ("/api/v1/admin/users", "get"),
        ("/api/v1/follow-sessions", "post"),
    ]:
        assert {"cookieAuth": []} in paths[path][method]["security"], path
    for path in ("/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/logout"):
        assert "security" not in paths[path]["post"], path


def test_examples_and_error_shapes_are_documented(client):
    spec = _spec(client)
    assert spec["components"]["schemas"]["Credentials"]["examples"][0]["email"] == "john@john.com"
    assert spec["components"]["schemas"]["StartRequest"]["examples"][0]["distance_m"] == 2.0
    unauthorized = spec["paths"]["/api/v1/users/me"]["get"]["responses"]["401"]
    assert unauthorized["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorOut")
    assert spec["info"]["version"] == "1.0.0"


def test_swagger_login_flow_works_with_the_cookie(client):
    """What a person does in Swagger: run login, then call a protected endpoint without pasting anything."""
    assert client.post("/api/v1/auth/login", json={"email": "john@john.com", "password": "123"}).status_code == 200
    assert client.get("/api/v1/users/me").status_code == 200
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/users/me").status_code == 401
