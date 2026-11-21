from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import messages
from ..config import Settings
from ..db import User
from ..security import get_current_user, get_db, get_settings
from ..usage import calls_used

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class MeOut(BaseModel):
    id: int
    email: str
    role: str
    api_calls_used: int
    free_calls_limit: int
    free_calls_exceeded: bool
    warning: str | None


@router.get("/me", response_model=MeOut, responses={401: {"description": "Not logged in"}})
def read_me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MeOut:
    """The logged-in user's profile and API consumption.

    `api_calls_used` includes this request, because it's counted after the response is built.
    """
    used = calls_used(db, user.id) + 1
    exceeded = used > settings.free_calls
    return MeOut(
        id=user.id,
        email=user.email,
        role=user.role,
        api_calls_used=used,
        free_calls_limit=settings.free_calls,
        free_calls_exceeded=exceeded,
        warning=messages.FREE_CALLS_EXHAUSTED.format(limit=settings.free_calls) if exceeded else None,
    )
