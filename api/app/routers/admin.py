"""Administrator-only endpoints. The role check happens here on the server, not in the client."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import ApiUsage, User
from ..security import get_db, require_admin

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
    responses={401: {"description": "Not logged in"}, 403: {"description": "Not an administrator"}},
)


class AdminUserOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: datetime
    total_requests: int


class EndpointStatOut(BaseModel):
    method: str
    endpoint: str
    total_requests: int


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db)) -> list[AdminUserOut]:
    """Every registered user with their total counted API requests. Password hashes are never returned."""
    rows = db.execute(
        select(User, func.count(ApiUsage.id))
        .outerjoin(ApiUsage, ApiUsage.user_id == User.id)
        .group_by(User.id)
        .order_by(User.id)
    ).all()
    return [
        AdminUserOut(id=u.id, email=u.email, role=u.role, created_at=u.created_at, total_requests=count)
        for u, count in rows
    ]


@router.get("/stats/endpoints", response_model=list[EndpointStatOut])
def endpoint_stats(db: Session = Depends(get_db)) -> list[EndpointStatOut]:
    """How many requests each endpoint has served, busiest first."""
    total = func.count(ApiUsage.id)
    rows = db.execute(
        select(ApiUsage.method, ApiUsage.endpoint, total)
        .group_by(ApiUsage.method, ApiUsage.endpoint)
        .order_by(total.desc(), ApiUsage.endpoint)
    ).all()
    return [EndpointStatOut(method=m, endpoint=e, total_requests=n) for m, e, n in rows]
