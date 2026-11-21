"""Drone3POV API (v1). Run with: uvicorn app.main:app"""

import logging
import os
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from . import messages
from .config import DEV_JWT_SECRET, Settings
from .db import User, make_session_factory
from .drone import DroneAdapter, SimulatedDrone
from .routers import admin, auth, sessions, users, vision
from .security import hash_password
from .usage import USAGE_HEADERS, UsageTracker
from .vision import PersonDetector

log = logging.getLogger("drone3pov")

# Demonstration accounts required by the course. Passwords are hashed like any other account.
DEMO_USERS = (
    ("john@john.com", "123", "user"),
    ("admin@admin.com", "111", "admin"),
)


def seed_demo_users(session_factory) -> None:
    with session_factory() as db:
        for email, password, role in DEMO_USERS:
            if db.scalar(select(User).where(User.email == email)) is None:
                db.add(User(email=email, password_hash=hash_password(password), role=role))
        db.commit()


def _default_drone() -> DroneAdapter:
    """DRONE=mini2 with BRIDGE_URL set uses the real Mini 2; anything else uses the simulator."""
    if os.environ.get("DRONE", "sim") == "mini2":
        from .mini2 import HttpBridgeTransport, Mini2Adapter

        return Mini2Adapter(HttpBridgeTransport(os.environ["BRIDGE_URL"]))
    return SimulatedDrone()


def create_app(settings: Settings | None = None, drone: DroneAdapter | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.jwt_secret == DEV_JWT_SECRET:
        log.warning("JWT_SECRET is not set; using the development secret. Set it before deploying.")

    app = FastAPI(
        title="Drone3POV API",
        version="1.0.0",
        description=(
            "Follow-me drone service: a DJI Mini 2 follows one consenting person and records the flight. "
            "Log in with `POST /api/v1/auth/login`; the API sets an HttpOnly cookie that authenticates "
            "every other request. A `Authorization: Bearer <token>` header also works for API clients.\n\n"
            f"Each user gets {settings.free_calls} free calls. Every counted response carries "
            "`X-Free-Calls-Used`, `X-Free-Calls-Limit` and `X-Free-Calls-Exceeded` headers."
        ),
        docs_url="/doc/",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )

    engine, session_factory = make_session_factory(settings.database_url)
    if settings.seed_demo_users:
        seed_demo_users(session_factory)

    app.state.settings = settings
    app.state.engine = engine
    app.state.SessionLocal = session_factory
    app.state.detector = PersonDetector(settings.model_path)
    app.state.drone = drone if drone is not None else _default_drone()
    app.state.sessions = {}
    app.state.active_id = None
    app.state.lock = threading.Lock()

    for router in (auth.router, users.router, admin.router, vision.router, sessions.router):
        app.include_router(router)

    @app.exception_handler(Exception)
    async def _server_error(_request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": messages.SERVER_ERROR})

    # Added last so it runs first: CORS headers are applied even to error responses.
    app.add_middleware(UsageTracker)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.client_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=USAGE_HEADERS,
    )
    return app


app = create_app()
