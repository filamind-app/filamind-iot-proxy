"""Pairing-flow business logic.

Phase 1 scope:
  * connect_box  — register/refresh a Box row, mint a PairingCode,
                   mirror to Redis with TTL.
  * poll_code    — read-only state of a code (pending/consumed/expired).
  * finalize     — atomic claim of a code by an Odoo db_uuid.
  * record_audit — append-only entry written on every state mutation.

License-gate, tenant resolution, and quota enforcement are stubbed
(`tenant_id=None` always) — Phase 4 wires them.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api import redis_store
from api.config import get_settings
from api.models import Audit, Box, PairingCode


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _generate_code() -> str:
    s = get_settings()
    return "".join(
        secrets.choice(s.pairing_code_alphabet) for _ in range(s.pairing_code_length)
    )


async def _unique_code(session: AsyncSession, attempts: int = 8) -> str:
    """Generate a code guaranteed not to collide with an unconsumed
    PairingCode row. The chance of collision in 32^8 space is microscopic
    but we still guard against it."""
    for _ in range(attempts):
        code = _generate_code()
        row = await session.scalar(
            select(PairingCode).where(PairingCode.code == code),
        )
        if row is None:
            return code
    raise RuntimeError("could not generate unique pairing code")


async def record_audit(
    session: AsyncSession,
    *,
    actor: str,
    event: str,
    box_id: UUID | None = None,
    tenant_id: UUID | None = None,
    payload: dict | None = None,
) -> None:
    session.add(
        Audit(
            actor=actor,
            event=event,
            box_id=box_id,
            tenant_id=tenant_id,
            payload=payload,
        ),
    )


async def connect_box(
    session: AsyncSession,
    *,
    serial_number: str,
    cert_subject: str | None,
) -> tuple[Box, PairingCode]:
    """Idempotent: existing Box keyed by serial_number is reused.
    A fresh PairingCode is always minted (the old one stays in DB
    but is no longer mirrored to Redis from this call)."""
    s = get_settings()

    box = await session.scalar(
        select(Box).where(Box.serial_number == serial_number),
    )
    if box is None:
        box = Box(serial_number=serial_number, status="pending")
        session.add(box)
        await session.flush()
    if cert_subject:
        box.cert_subject = cert_subject
    box.last_seen = _utcnow()

    code = await _unique_code(session)
    expires_at = _utcnow() + timedelta(seconds=s.pairing_code_ttl_seconds)
    pc = PairingCode(
        code=code,
        box_id=box.id,
        tenant_id=box.tenant_id,
        expires_at=expires_at,
    )
    session.add(pc)

    await record_audit(
        session,
        actor="box",
        event="connect",
        box_id=box.id,
        payload={"serial_number": serial_number},
    )

    await session.flush()
    await redis_store.cache_pairing_code(code, str(box.id), s.pairing_code_ttl_seconds)
    return box, pc


async def poll_code(session: AsyncSession, code: str) -> dict:
    pc = await session.scalar(
        select(PairingCode).where(PairingCode.code == code),
    )
    if pc is None:
        return {"code": code, "status": "unknown"}

    box = await session.scalar(select(Box).where(Box.id == pc.box_id))

    if pc.consumed_at is not None:
        return {
            "code": code,
            "status": "consumed",
            "box_id": pc.box_id,
            "paired_db_uuid": box.paired_db_uuid if box else None,
            "paired_server_url": box.paired_server_url if box else None,
            "paired_at": box.paired_at if box else None,
        }

    if pc.expires_at <= _utcnow():
        return {"code": code, "status": "expired", "box_id": pc.box_id}

    return {"code": code, "status": "pending", "box_id": pc.box_id}


async def finalize(
    session: AsyncSession,
    *,
    code: str,
    db_uuid: str,
    server_url: str,
) -> Box:
    """Atomic claim: mark PairingCode consumed and write pairing details
    to the Box row. Raises ValueError on bad/expired/consumed codes."""
    pc = await session.scalar(
        select(PairingCode).where(PairingCode.code == code).with_for_update(),
    )
    if pc is None:
        raise ValueError("unknown_code")
    if pc.consumed_at is not None:
        raise ValueError("already_consumed")
    if pc.expires_at <= _utcnow():
        raise ValueError("expired")

    box = await session.scalar(
        select(Box).where(Box.id == pc.box_id).with_for_update(),
    )
    if box is None:
        raise ValueError("box_missing")

    now = _utcnow()
    pc.consumed_at = now
    pc.consumed_by_db_uuid = db_uuid
    box.paired_db_uuid = db_uuid
    box.paired_server_url = server_url
    box.paired_at = now
    box.status = "paired"

    await record_audit(
        session,
        actor="odoo",
        event="finalize",
        box_id=box.id,
        payload={"db_uuid": db_uuid, "server_url": server_url},
    )

    await session.flush()
    await redis_store.invalidate_pairing_code(code)
    return box
