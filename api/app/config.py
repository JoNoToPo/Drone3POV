"""Settings read from environment variables. Secrets never live in the source code."""

import os
from dataclasses import dataclass
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH = API_DIR / "models" / "yolov10n" / "onnx" / "model.onnx"
DEV_JWT_SECRET = "dev-only-secret-change-me-before-deploying"


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _database_url(raw: str) -> str:
    # Hosts hand out postgres:// URLs; SQLAlchemy needs the driver named explicitly.
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            return "postgresql+psycopg://" + raw[len(prefix):]
    return raw


@dataclass(frozen=True)
class Settings:
    database_url: str = f"sqlite:///{API_DIR / 'drone3pov.db'}"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_minutes: int = 60
    # Cross-origin cookies need SameSite=None and Secure (HTTPS). Local HTTP dev uses Lax.
    cookie_secure: bool = True
    cookie_samesite: str = "none"
    client_origins: tuple[str, ...] = ("http://localhost:5173",)
    model_path: Path = DEFAULT_MODEL_PATH
    free_calls: int = 20
    seed_demo_users: bool = True
    max_upload_bytes: int = 8 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        secure = _bool("COOKIE_SECURE", True)
        origins = os.environ.get("CLIENT_ORIGINS", "http://localhost:5173")
        return cls(
            database_url=_database_url(os.environ.get("DATABASE_URL", cls.database_url)),
            jwt_secret=os.environ.get("JWT_SECRET", DEV_JWT_SECRET),
            jwt_minutes=int(os.environ.get("JWT_MINUTES", "60")),
            cookie_secure=secure,
            cookie_samesite=os.environ.get("COOKIE_SAMESITE", "none" if secure else "lax"),
            client_origins=tuple(o.strip().rstrip("/") for o in origins.split(",") if o.strip()),
            model_path=Path(os.environ.get("MODEL_PATH", str(DEFAULT_MODEL_PATH))),
            free_calls=int(os.environ.get("FREE_CALLS", "20")),
            seed_demo_users=_bool("SEED_DEMO_USERS", True),
        )
