import io

from PIL import Image

from app import messages
from app.usage import HEADER_EXCEEDED, HEADER_LIMIT, HEADER_USED

from .conftest import CLIENT_ORIGIN, FIXTURES, login

ME = "/api/v1/users/me"
DETECT = "/api/v1/vision/detect"


def _png(width=320, height=240, colour=(40, 120, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buf, format="PNG")
    return buf.getvalue()


# --- usage tracking ------------------------------------------------------

def test_auth_requests_are_not_counted(client):
    login(client, "john@john.com", "123")
    login(client, "john@john.com", "123")
    assert client.get(ME).json()["api_calls_used"] == 1


def test_each_counted_call_increments_usage(user_client):
    for expected in (1, 2, 3):
        r = user_client.get(ME)
        assert r.json()["api_calls_used"] == expected
        assert r.headers[HEADER_USED] == str(expected)
        assert r.headers[HEADER_LIMIT] == "20"


def test_service_continues_after_free_calls_with_warning(user_client):
    for _ in range(20):
        r = user_client.get(ME)
        assert r.headers[HEADER_EXCEEDED] == "false"
    r = user_client.get(ME)
    assert r.status_code == 200  # still served
    assert r.headers[HEADER_EXCEEDED] == "true"
    assert r.json()["free_calls_exceeded"] is True
    assert r.json()["warning"] == messages.FREE_CALLS_EXHAUSTED.format(limit=20)


def test_usage_headers_are_readable_cross_origin(user_client):
    r = user_client.get(ME, headers={"Origin": CLIENT_ORIGIN})
    exposed = r.headers["access-control-expose-headers"]
    assert HEADER_USED in exposed and HEADER_EXCEEDED in exposed


def test_failed_requests_by_logged_in_users_still_count(user_client):
    user_client.get("/api/v1/follow-sessions/missing")  # 404
    stats = user_client.get(ME).json()
    assert stats["api_calls_used"] == 2


def test_admin_stats_come_from_server_data(admin_client, make_client):
    john = make_client()
    login(john, "john@john.com", "123")
    john.get(ME)
    john.get(ME)
    john.get("/api/v1/drone/status")

    endpoints = {(e["method"], e["endpoint"]): e["total_requests"] for e in admin_client.get("/api/v1/admin/stats/endpoints").json()}
    assert endpoints[("GET", "/api/v1/users/me")] == 2
    assert endpoints[("GET", "/api/v1/drone/status")] == 1

    users = {u["email"]: u["total_requests"] for u in admin_client.get("/api/v1/admin/users").json()}
    assert users["john@john.com"] == 3


def test_route_templates_group_requests_by_endpoint(admin_client, user_client):
    user_client.get("/api/v1/follow-sessions/a")
    user_client.get("/api/v1/follow-sessions/b")
    endpoints = {(e["method"], e["endpoint"]): e["total_requests"] for e in admin_client.get("/api/v1/admin/stats/endpoints").json()}
    assert endpoints[("GET", "/api/v1/follow-sessions/{session_id}")] == 2


# --- self-hosted person detection ---------------------------------------

def test_detect_needs_login(client):
    r = client.post(DETECT, files={"image": ("x.png", _png(), "image/png")})
    assert r.status_code == 401


def test_detect_finds_people_in_a_real_photo(user_client):
    data = (FIXTURES / "people.jpg").read_bytes()
    r = user_client.post(DETECT, files={"image": ("people.jpg", data, "image/jpeg")})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "onnx-community/yolov10n"
    assert body["people_count"] >= 3
    first = body["people"][0]
    assert first["confidence"] >= 0.8
    assert -1 <= first["center_offset_x"] <= 1
    x1, y1, x2, y2 = first["box"]
    assert 0 <= x1 < x2 <= body["image_width"] and 0 <= y1 < y2 <= body["image_height"]


def test_detect_returns_no_people_for_a_plain_image(user_client):
    r = user_client.post(DETECT, files={"image": ("blank.png", _png(), "image/png")})
    assert r.status_code == 200
    assert r.json()["people_count"] == 0


def test_detect_rejects_non_images(user_client):
    r = user_client.post(DETECT, files={"image": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_detect_rejects_corrupt_images(user_client):
    r = user_client.post(DETECT, files={"image": ("broken.png", b"not really a png", "image/png")})
    assert r.status_code == 422


def test_detect_rejects_huge_uploads(make_client):
    c = make_client(max_upload_bytes=1000)
    login(c, "john@john.com", "123")
    r = c.post(DETECT, files={"image": ("big.png", _png(800, 800), "image/png")})
    assert r.status_code == 413


def test_detect_fails_when_model_file_is_missing(make_client, tmp_path):
    c = make_client(model_path=tmp_path / "missing.onnx")
    login(c, "john@john.com", "123")
    r = c.post(DETECT, files={"image": ("x.png", _png(), "image/png")})
    assert r.status_code == 503
    assert r.json()["detail"] == messages.MODEL_UNAVAILABLE
