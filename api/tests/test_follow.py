import pytest
from fastapi.testclient import TestClient

from app import safety
from app.session import FollowSession, Observation, State
from app.safety import SafetyError, validate_settings

from .conftest import login


# --- safety limits -------------------------------------------------------

def test_defaults_are_valid():
    s = validate_settings("third_person", safety.DEFAULT_DISTANCE_M, safety.DEFAULT_HEIGHT_M)
    assert s.distance_m == 2.0


@pytest.mark.parametrize("distance", [1.0, 3.5])
def test_distance_out_of_range_rejected(distance):
    with pytest.raises(SafetyError):
        validate_settings("third_person", distance, 1.6)


def test_reverse_mode_not_allowed_yet():
    with pytest.raises(SafetyError):
        validate_settings("reverse_third_person", 2.0, 1.6)


def test_speed_is_clamped():
    assert safety.clamp_speed(5.0) == safety.MAX_SPEED_MPS
    assert safety.clamp_speed(-5.0) == -safety.MAX_SPEED_MPS


# --- state machine -------------------------------------------------------

def make_session():
    return FollowSession(settings=validate_settings("third_person", 2.0, 1.6))


def test_search_lock_follow_path():
    s = make_session()
    assert s.state == State.SEARCHING
    assert s.tick(Observation(subject_visible=True, distance_m=2.0)) == State.LOCKED
    assert s.tick(Observation(subject_visible=True, distance_m=2.0)) == State.FOLLOWING


def test_lost_then_reacquired_returns_to_following():
    s = make_session()
    s.tick(Observation(subject_visible=True, distance_m=2.0))
    s.tick(Observation(subject_visible=True, distance_m=2.0))
    assert s.tick(Observation(subject_visible=False, lost_for_s=1.0)) == State.LOST
    assert s.tick(Observation(subject_visible=True, distance_m=2.0)) == State.FOLLOWING


def test_lost_too_long_lands():
    s = make_session()
    s.tick(Observation(subject_visible=True, distance_m=2.0))
    s.tick(Observation(subject_visible=True, distance_m=2.0))
    s.tick(Observation(subject_visible=False, lost_for_s=safety.LOST_LAND_S))
    assert s.state == State.LANDING
    assert s.end_reason == "subject_lost"


@pytest.mark.parametrize(
    "obs, reason",
    [
        (Observation(subject_visible=True, link_ok=False), "link_lost"),
        (Observation(subject_visible=True, battery_pct=10), "low_battery"),
        (Observation(subject_visible=True, tof_mm=300), "obstacle_too_close"),
        (Observation(subject_visible=True, distance_m=1.0), "subject_too_close"),
    ],
)
def test_safety_triggers_land(obs, reason):
    s = make_session()
    s.tick(obs)
    assert s.state == State.LANDING
    assert s.end_reason == reason


# --- API -----------------------------------------------------------------

SESSIONS = "/api/v1/follow-sessions"


def test_sessions_need_login(client):
    assert client.post(SESSIONS, json={}).status_code == 401


def test_start_and_stop_session(user_client):
    r = user_client.post(SESSIONS, json={"distance_m": 2.0})
    assert r.status_code == 202
    body = r.json()
    assert body["state"] == "searching"
    assert user_client.get(f"{SESSIONS}/{body['id']}").json()["id"] == body["id"]

    stopped = user_client.post(f"{SESSIONS}/{body['id']}/stop").json()
    assert stopped["state"] == "finished"
    assert stopped["end_reason"] == "stopped_by_user"


def test_second_session_rejected_while_one_is_active(user_client):
    assert user_client.post(SESSIONS, json={}).status_code == 202
    assert user_client.post(SESSIONS, json={}).status_code == 409


def test_bad_distance_is_422(user_client):
    assert user_client.post(SESSIONS, json={"distance_m": 9}).status_code == 422


def test_unknown_fields_rejected(user_client):
    assert user_client.post(SESSIONS, json={"max_speed": 50}).status_code == 422


def test_missing_session_is_404(user_client):
    assert user_client.get(f"{SESSIONS}/nope").status_code == 404


def test_users_cannot_touch_each_others_sessions(user_client):
    session_id = user_client.post(SESSIONS, json={}).json()["id"]

    other = TestClient(user_client.app)  # same app, separate cookie jar
    other.post("/api/v1/auth/register", json={"email": "tom@example.com", "password": "secret"})
    login(other, "tom@example.com", "secret")
    assert other.get(f"{SESSIONS}/{session_id}").status_code == 403
    assert other.post(f"{SESSIONS}/{session_id}/stop").status_code == 403


def test_emergency_stop_clears_active_session(user_client):
    user_client.post(SESSIONS, json={})
    r = user_client.post("/api/v1/drone/emergency-stop")
    assert r.status_code == 200
    assert "stopped" in r.json()["message"]
    # A new session can start once the emergency stop has cleared the lock.
    assert user_client.post(SESSIONS, json={}).status_code == 202
