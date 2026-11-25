"""Follow sessions and direct drone control. The cloud API sets goals; it never flies the control loop."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from .. import messages, safety
from ..db import User
from ..security import get_current_user
from ..session import FollowSession, State
from ..schemas import error

router = APIRouter(prefix="/api/v1", tags=["follow sessions"], responses={401: error("Not logged in")})


class StartRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"mode": "third_person", "distance_m": 2.0, "height_m": 1.6}]},
    )

    mode: Literal["third_person"] = "third_person"
    distance_m: float = Field(default=safety.DEFAULT_DISTANCE_M)
    height_m: float = Field(default=safety.DEFAULT_HEIGHT_M)


class SessionOut(BaseModel):
    id: str
    state: State
    mode: str
    distance_m: float
    height_m: float
    end_reason: str | None


class DroneStatus(BaseModel):
    battery_pct: int
    height_m: float
    tof_mm: int | None
    link_ok: bool


class MessageOut(BaseModel):
    message: str


def _out(s: FollowSession) -> SessionOut:
    return SessionOut(
        id=s.id,
        state=s.state,
        mode=s.settings.mode,
        distance_m=s.settings.distance_m,
        height_m=s.settings.height_m,
        end_reason=s.end_reason,
    )


def _owned_session(request: Request, session_id: str, user: User) -> FollowSession:
    session = request.app.state.sessions.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, messages.SESSION_NOT_FOUND)
    if session.owner_id != user.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, messages.SESSION_NOT_YOURS)
    return session


@router.post("/follow-sessions", status_code=status.HTTP_202_ACCEPTED, response_model=SessionOut,
             responses={409: error("Drone already in use"), 422: error("Setting outside safety limits")})
def start_session(body: StartRequest, request: Request, user: User = Depends(get_current_user)) -> SessionOut:
    """Start a follow session. The drone takes off and searches for the subject."""
    try:
        settings = safety.validate_settings(body.mode, body.distance_m, body.height_m)
    except safety.SafetyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    state = request.app.state
    with state.lock:
        if state.active_id is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, messages.DRONE_BUSY)
        session = FollowSession(settings=settings, owner_id=user.id)
        state.sessions[session.id] = session
        state.active_id = session.id
        state.drone.connect()
        state.drone.takeoff()
    return _out(session)


@router.get("/follow-sessions/{session_id}", response_model=SessionOut,
            responses={403: error("Not your session"), 404: error("No such session")})
def read_session(session_id: str, request: Request, user: User = Depends(get_current_user)) -> SessionOut:
    """State of one of your follow sessions."""
    return _out(_owned_session(request, session_id, user))


@router.post("/follow-sessions/{session_id}/stop", response_model=SessionOut,
             responses={403: error("Not your session"), 404: error("No such session")})
def stop_session(session_id: str, request: Request, user: User = Depends(get_current_user)) -> SessionOut:
    """Stop following and land."""
    session = _owned_session(request, session_id, user)
    state = request.app.state
    with state.lock:
        session.stop("stopped_by_user")
        state.drone.land()
        session.confirm_landed()
        if state.active_id == session_id:
            state.active_id = None
    return _out(session)


@router.get("/drone/status", response_model=DroneStatus)
def drone_status(request: Request, _user: User = Depends(get_current_user)) -> DroneStatus:
    """Battery, height and link state."""
    t = request.app.state.drone.telemetry()
    return DroneStatus(battery_pct=t.battery_pct, height_m=t.height_m, tof_mm=t.tof_mm, link_ok=t.link_ok)


@router.post("/drone/emergency-stop", response_model=MessageOut)
def emergency_stop(request: Request, _user: User = Depends(get_current_user)) -> MessageOut:
    """Stop the motors now. Any logged-in user may press it; it skips the session lock on purpose."""
    state = request.app.state
    state.drone.emergency_stop()
    for session in state.sessions.values():
        if session.state != State.FINISHED:
            session.stop("emergency_stop")
            session.confirm_landed()
    state.active_id = None
    return MessageOut(message=messages.DRONE_STOPPED)
