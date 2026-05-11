"""Liveness + readiness."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api import redis_store
from api.db import get_session
from api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    db_ok = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_ok = f"error: {type(exc).__name__}"

    redis_ok = "ok"
    try:
        pong = await redis_store.get_redis().ping()
        if not pong:
            redis_ok = "error: no pong"
    except Exception as exc:  # noqa: BLE001
        redis_ok = f"error: {type(exc).__name__}"

    overall = "ok" if db_ok == "ok" and redis_ok == "ok" else "degraded"
    return HealthResponse(status=overall, db=db_ok, redis=redis_ok)
