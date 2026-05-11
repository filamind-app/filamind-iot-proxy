"""Pairing endpoints — wire-compatible-ish with iot-proxy.odoo.com.

  POST /iot/connect           box  -> proxy
  GET  /iot/poll/{code}       odoo -> proxy   (also used by box for status)
  POST /iot/finalize          odoo -> proxy
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db import get_session
from api.schemas import (
    ConnectRequest,
    ConnectResponse,
    FinalizeRequest,
    FinalizeResponse,
    PollResponse,
)
from api.services import pairing as svc

router = APIRouter(prefix="/iot", tags=["iot"])


@router.post("/connect", response_model=ConnectResponse)
async def connect(
    body: ConnectRequest,
    session: AsyncSession = Depends(get_session),
) -> ConnectResponse:
    box, code = await svc.connect_box(
        session,
        serial_number=body.serial_number,
        cert_subject=body.cert_subject,
    )
    await session.commit()
    return ConnectResponse(
        box_id=box.id,
        pairing_code=code.code,
        expires_at=code.expires_at,
        proxy_public_url=get_settings().proxy_public_url,
    )


@router.get("/poll/{code}", response_model=PollResponse)
async def poll(
    code: str,
    session: AsyncSession = Depends(get_session),
) -> PollResponse:
    state = await svc.poll_code(session, code)
    return PollResponse(**state)


@router.post("/finalize", response_model=FinalizeResponse)
async def finalize(
    body: FinalizeRequest,
    session: AsyncSession = Depends(get_session),
) -> FinalizeResponse:
    try:
        box = await svc.finalize(
            session,
            code=body.code,
            db_uuid=body.db_uuid,
            server_url=body.server_url,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc),
        ) from exc

    await session.commit()
    return FinalizeResponse(
        box_id=box.id,
        paired_db_uuid=box.paired_db_uuid or "",
        paired_server_url=box.paired_server_url or "",
        paired_at=box.paired_at,  # type: ignore[arg-type]
    )
