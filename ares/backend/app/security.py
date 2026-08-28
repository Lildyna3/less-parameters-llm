"""Optional access control for the deployed ARES web app.

When ARES_ACCESS_TOKEN is set, every API and WebSocket client must present it
(header `X-ARES-Token`, `Authorization: Bearer …`, or an `access_token` query
parameter for WebSockets, which cannot set headers from the browser).

The token lives in the server environment and, on the client, only in the
browser's localStorage after the user types it — it is never compiled into the
frontend bundle. When no token is configured ARES stays open, which is correct
for a laptop-local install and wrong for a public deployment; the System
status surfaces that distinction honestly.
"""

from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import SecuritySettings
from .logging_setup import register_secret


def extract_token(request: Request) -> str | None:
    header = request.headers.get("x-ares-token")
    if header:
        return header
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.query_params.get("access_token")


def token_ok(settings: SecuritySettings, candidate: str | None) -> bool:
    if not settings.access_token:
        return True
    return bool(candidate) and hmac.compare_digest(candidate, settings.access_token)


class AccessTokenMiddleware(BaseHTTPMiddleware):
    """Guards /api/* when a token is configured. Static assets stay public so
    the login screen itself can load; every data path is protected."""

    def __init__(self, app, settings: SecuritySettings) -> None:
        super().__init__(app)
        self.settings = settings
        register_secret(settings.access_token)

    async def dispatch(self, request: Request, call_next):
        if not self.settings.access_token:
            return await call_next(request)

        path = request.url.path
        needs_auth = path.startswith("/api/")
        if not needs_auth or path in self.settings.public_paths:
            return await call_next(request)
        # Browsers send a preflight without credentials.
        if request.method == "OPTIONS":
            return await call_next(request)

        if not token_ok(self.settings, extract_token(request)):
            return JSONResponse(
                {"detail": "Access token required or invalid."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)
