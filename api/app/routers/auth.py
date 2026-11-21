import re

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import messages
from ..config import Settings
from ..db import User
from ..security import (
    clear_auth_cookie,
    create_token,
    get_db,
    get_settings,
    hash_password,
    set_auth_cookie,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    # extra="forbid" blocks mass assignment: a client can't send "role": "admin".
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if len(value) > 254 or not EMAIL_PATTERN.match(value):
            raise ValueError(messages.EMAIL_INVALID)
        return value

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        # bcrypt only uses the first 72 bytes, so longer passwords are refused.
        if not 3 <= len(value) or len(value.encode("utf-8")) > 72:
            raise ValueError(messages.PASSWORD_LENGTH)
        return value


class UserOut(BaseModel):
    id: int
    email: str
    role: str


class MessageOut(BaseModel):
    message: str


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut,
             responses={409: {"description": "Email already registered"}})
def register(body: Credentials, db: Session = Depends(get_db)) -> UserOut:
    """Create a regular user account. New accounts always get the `user` role."""
    user = User(email=body.email, password_hash=hash_password(body.password), role="user")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, messages.EMAIL_TAKEN) from None
    return UserOut(id=user.id, email=user.email, role=user.role)


@router.post("/login", response_model=UserOut, responses={401: {"description": "Wrong email or password"}})
def login(
    body: Credentials,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    """Check the password and set a signed JWT in an HttpOnly cookie."""
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        # Same message for both cases, so the response doesn't reveal which emails exist.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, messages.LOGIN_FAILED)
    set_auth_cookie(response, create_token(user, settings), settings)
    return UserOut(id=user.id, email=user.email, role=user.role)


@router.post("/logout", response_model=MessageOut)
def logout(response: Response, settings: Settings = Depends(get_settings)) -> MessageOut:
    """Clear the auth cookie."""
    clear_auth_cookie(response, settings)
    return MessageOut(message=messages.LOGGED_OUT)
