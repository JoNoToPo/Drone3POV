"""Follow-me API (v1). Cloud side only: it sets goals and limits and never sits in the control loop."""

import os
import threading
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from . import safety
from .drone import DroneAdapter, SimulatedDrone
from .session import FollowSession, State

API_KEY = os.environ.get("FOLLOW_API_KEY", "dev-key")


class StartRequest(BaseModel):
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


def create_app(drone: DroneAdapter | None = None) -> FastAPI:
    app = FastAPI(title="Follow-me drone API", version="1.0.0")
    app.state.drone = drone if drone is not None else SimulatedDrone()
    app.state.sessions: dict[str, FollowSession] = {}
    app.state.active_id: str | None = None
    app.state.lock = threading.Lock()

    def require_key(x_api_key: str | None = Header(default=None)) -> None:
        if x_api_key != API_KEY:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid API key")

    def get_session(session_id: str) -> FollowSession:
        session = app.state.sessions.get(session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
        return session

    @app.post("/v1/follow-sessions", status_code=status.HTTP_202_ACCEPTED,
              response_model=SessionOut, dependencies=[Depends(require_key)])
    def start_session(body: StartRequest) -> SessionOut:
        try:
            settings = safety.validate_settings(body.mode, body.distance_m, body.height_m)
        except safety.SafetyError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        with app.state.lock:
            if app.state.active_id is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, "another session already controls the drone")
            session = FollowSession(settings=settings)
            app.state.sessions[session.id] = session
            app.state.active_id = session.id
            app.state.drone.connect()
            app.state.drone.takeoff()
        return _out(session)

    @app.get("/v1/follow-sessions/{session_id}", response_model=SessionOut,
             dependencies=[Depends(require_key)])
    def read_session(session_id: str) -> SessionOut:
        return _out(get_session(session_id))

    @app.post("/v1/follow-sessions/{session_id}/stop", response_model=SessionOut,
              dependencies=[Depends(require_key)])
    def stop_session(session_id: str) -> SessionOut:
        session = get_session(session_id)
        with app.state.lock:
            session.stop("stopped_by_user")
            app.state.drone.land()
            session.confirm_landed()
            if app.state.active_id == session_id:
                app.state.active_id = None
        return _out(session)

    @app.get("/v1/drone/status", response_model=DroneStatus, dependencies=[Depends(require_key)])
    def drone_status() -> DroneStatus:
        t = app.state.drone.telemetry()
        return DroneStatus(battery_pct=t.battery_pct, height_m=t.height_m, tof_mm=t.tof_mm, link_ok=t.link_ok)

    @app.post("/v1/drone/emergency-stop", dependencies=[Depends(require_key)])
    def emergency_stop() -> dict:
        # Skips the session lock on purpose: it must never wait behind anything.
        app.state.drone.emergency_stop()
        for session in app.state.sessions.values():
            if session.state not in (State.FINISHED,):
                session.stop("emergency_stop")
                session.confirm_landed()
        app.state.active_id = None
        return {"status": "stopped"}

    return app


def _out(s: FollowSession) -> SessionOut:
    return SessionOut(
        id=s.id,
        state=s.state,
        mode=s.settings.mode,
        distance_m=s.settings.distance_m,
        height_m=s.settings.height_m,
        end_reason=s.end_reason,
    )


def _default_drone() -> DroneAdapter:
    """DRONE=mini2 with BRIDGE_URL set uses the real Mini 2; anything else uses the simulator."""
    if os.environ.get("DRONE", "sim") == "mini2":
        from .mini2 import HttpBridgeTransport, Mini2Adapter

        return Mini2Adapter(HttpBridgeTransport(os.environ["BRIDGE_URL"]))
    return SimulatedDrone()


app = create_app(_default_drone())
