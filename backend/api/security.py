"""Operator bearer-token auth for /admin/*.

Single-token model: a long random string in `ADMIN_TOKEN` env. Constant-time
comparison via `secrets.compare_digest` so we don't leak by timing.
Phase 4 expansion (multi-operator, scopes, rotation) happens later.
"""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from api.config import get_settings


async def require_admin(authorization: str | None = Header(default=None)) -> None:
    expected = get_settings().admin_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin_token_not_configured",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_bearer",
            headers={"WWW-Authenticate": "Bearer"},
        )
    presented = authorization.split(" ", 1)[1].strip()
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="invalid_token",
        )
