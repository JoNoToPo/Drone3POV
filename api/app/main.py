"""Drone3POV API (v1). Run with: uvicorn app.main:app"""

import logging
import os
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
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


API_DESCRIPTION = """
Follow-me drone service: a DJI Mini 2 follows one consenting person and records the flight.
The AI is person detection with a self-hosted model,
[onnx-community/yolov10n](https://huggingface.co/onnx-community/yolov10n), run on this server.

### Testing in Swagger
1. Open **auth → POST /api/v1/auth/login**, click **Try it out**, and **Execute** the example body
   (`john@john.com` / `123` for a user, `admin@admin.com` / `111` for an administrator).
2. The response sets an HttpOnly cookie. Every other **Try it out** on this page sends it automatically,
   so protected endpoints now work. You don't need the **Authorize** button in the browser.
3. **POST /api/v1/auth/logout** clears the cookie. Protected endpoints then return 401.

For Postman or curl, send the JWT as `Authorization: Bearer <token>` instead.

### Free calls
Each user gets {free_calls} free calls. Every counted response carries `X-Free-Calls-Used`,
`X-Free-Calls-Limit` and `X-Free-Calls-Exceeded` headers. Login, registration, logout and these
docs are not counted, and the service keeps working after the limit.

### Errors
Every error response is JSON with a `detail` message, e.g. `{{"detail": "Log in to use this service."}}`.
"""

OPENAPI_TAGS = [
    {"name": "auth", "description": "Register, log in and log out. Not counted toward free calls."},
    {"name": "users", "description": "The logged-in user's profile and API consumption."},
    {"name": "vision (AI)", "description": "Person detection with the self-hosted YOLOv10n model."},
    {"name": "follow sessions", "description": "Start, read and stop follow sessions, and control the drone."},
    {"name": "admin", "description": "Administrator only: users and API usage statistics."},
]


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


def check_production_settings(settings: Settings) -> None:
    """On a host (Vercel sets VERCEL=1), refuse to start with settings that are unsafe or can't work."""
    if not (os.environ.get("VERCEL") or os.environ.get("REQUIRE_PRODUCTION_SETTINGS")):
        return
    problems = []
    if settings.jwt_secret == DEV_JWT_SECRET or len(settings.jwt_secret) < 32:
        problems.append("JWT_SECRET must be set to a random value of at least 32 characters.")
    if settings.database_url.startswith("sqlite"):
        problems.append("DATABASE_URL must point to Postgres; the host's file system is read-only.")
    if problems:
        raise RuntimeError("Refusing to start: " + " ".join(problems))


def create_app(settings: Settings | None = None, drone: DroneAdapter | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    check_production_settings(settings)
    if settings.jwt_secret == DEV_JWT_SECRET:
        log.warning("JWT_SECRET is not set; using the development secret. Set it before deploying.")

    app = FastAPI(
        title="Drone3POV API",
        version="1.0.0",
        description=API_DESCRIPTION.format(free_calls=settings.free_calls),
        openapi_tags=OPENAPI_TAGS,
        docs_url="/doc/",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
        swagger_ui_parameters={
            "persistAuthorization": True,  # keep a pasted Bearer token across page reloads
            "withCredentials": True,  # send the login cookie with "Try it out" requests
            "displayRequestDuration": True,
            "tryItOutEnabled": True,
            "filter": True,
        },
    )

    @app.get("/doc", include_in_schema=False)
    def _doc_without_slash() -> RedirectResponse:
        return RedirectResponse("/doc/")

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
