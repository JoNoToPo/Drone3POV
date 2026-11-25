"""Password hashing, JWT handling and the auth dependencies used by protected routes."""

from collections.abc import Iterator
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response, Security, status
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import messages
from .config import Settings
from .db import User, utcnow

COOKIE_NAME = "access_token"
ALGORITHM = "HS256"

# Declared as security schemes so the OpenAPI docs mark protected routes and show an Authorize button.
# auto_error=False lets get_current_user return the API's own 401 messages.
cookie_scheme = APIKeyCookie(
    name=COOKIE_NAME,
    scheme_name="cookieAuth",
    description="Set by POST /api/v1/auth/login. Browsers (and Swagger UI on this site) send it automatically.",
    auto_error=False,
)
bearer_scheme = HTTPBearer(
    scheme_name="bearerAuth",
    bearerFormat="JWT",
    description="For API clients such as Postman: send the same JWT as `Authorization: Bearer <token>`.",
    auto_error=False,
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def create_token(user: User, settings: Settings) -> str:
    now = utcnow()
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def set_auth_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.jwt_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def clear_auth_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        COOKIE_NAME,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    request: Request,
    cookie_token: str | None = Security(cookie_scheme),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    token = cookie_token or (bearer.credentials if bearer else None)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, messages.NOT_LOGGED_IN)
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, messages.SESSION_EXPIRED) from None
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, messages.TOKEN_INVALID) from None

    user = db.get(User, int(payload.get("sub", 0)))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, messages.TOKEN_INVALID)
    # The usage tracker reads this to know whose request it was.
    request.state.user_id = user.id
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    # The role is re-read from the database on every request, not trusted from the token.
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, messages.ADMIN_ONLY)
    return user
