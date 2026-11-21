"""Counts each authenticated request to a functional endpoint and flags when the free calls run out.

Not counted: registration, login, logout, documentation and CORS preflight requests.
The count lives in the database; the browser never decides it.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .db import ApiUsage

API_PREFIX = "/api/v1/"
EXCLUDED_PREFIXES = ("/api/v1/auth/",)

HEADER_USED = "X-Free-Calls-Used"
HEADER_LIMIT = "X-Free-Calls-Limit"
HEADER_EXCEEDED = "X-Free-Calls-Exceeded"
USAGE_HEADERS = [HEADER_USED, HEADER_LIMIT, HEADER_EXCEEDED]


def calls_used(db: Session, user_id: int) -> int:
    return db.scalar(select(func.count(ApiUsage.id)).where(ApiUsage.user_id == user_id)) or 0


def is_counted(method: str, path: str) -> bool:
    if method == "OPTIONS" or not path.startswith(API_PREFIX):
        return False
    return not path.startswith(EXCLUDED_PREFIXES)


class UsageTracker(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        user_id = getattr(request.state, "user_id", None)
        if user_id is None or not is_counted(request.method, request.url.path):
            return response

        route = request.scope.get("route")
        endpoint = getattr(route, "path", request.url.path)
        settings = request.app.state.settings
        with request.app.state.SessionLocal() as db:
            db.add(ApiUsage(
                user_id=user_id,
                method=request.method,
                endpoint=endpoint,
                status_code=response.status_code,
            ))
            db.commit()
            used = calls_used(db, user_id)

        response.headers[HEADER_USED] = str(used)
        response.headers[HEADER_LIMIT] = str(settings.free_calls)
        response.headers[HEADER_EXCEEDED] = "true" if used > settings.free_calls else "false"
        return response
