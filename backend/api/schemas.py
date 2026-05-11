"""Pydantic v2 request/response schemas.

Wire formats are intentionally close to upstream `iot-proxy.odoo.com`
so existing IoT-Box code can talk to us with minimal patching:
  - POST /iot/connect            (box -> proxy, register + get code)
  - GET  /iot/poll/<code>        (Odoo -> proxy, poll for pairing)
  - POST /iot/finalize           (Odoo -> proxy, claim a code)
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# -- Connect --------------------------------------------------------------

class ConnectRequest(BaseModel):
    """Box announces itself. The serial_number is whatever the box decides
    is stable — we don't assume Pi serial vs MAC vs other."""

    serial_number: str = Field(min_length=4, max_length=255)
    cert_subject: str | None = Field(default=None, max_length=255)


class ConnectResponse(BaseModel):
    box_id: UUID
    pairing_code: str
    expires_at: datetime
    proxy_public_url: str


# -- Poll -----------------------------------------------------------------

class PollResponse(BaseModel):
    """Returned to whichever party (Odoo or box) is polling for state."""

    code: str
    status: str  # 'pending' | 'consumed' | 'expired' | 'unknown'
    box_id: UUID | None = None
    paired_db_uuid: str | None = None
    paired_server_url: str | None = None
    paired_at: datetime | None = None


# -- Finalize -------------------------------------------------------------

class FinalizeRequest(BaseModel):
    """Odoo (or operator) claims a pairing code on behalf of a database."""

    code: str = Field(min_length=4, max_length=16)
    db_uuid: str = Field(min_length=8, max_length=64)
    server_url: str = Field(min_length=8, max_length=512)


class FinalizeResponse(BaseModel):
    box_id: UUID
    paired_db_uuid: str
    paired_server_url: str
    paired_at: datetime


# -- Admin ----------------------------------------------------------------

class BoxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID | None
    serial_number: str
    paired_db_uuid: str | None
    paired_server_url: str | None
    paired_at: datetime | None
    last_seen: datetime | None
    status: str
    created_at: datetime


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    plan: str
    box_quota: int
    contact_email: str | None
    license_key: str | None
    license_expires: datetime | None
    created_at: datetime


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    plan: str = Field(default="free", max_length=32)
    box_quota: int = Field(default=5, ge=0, le=10_000)
    contact_email: str | None = Field(default=None, max_length=255)
    license_key: str | None = Field(default=None, max_length=255)
    license_expires: datetime | None = None


class TenantPatch(BaseModel):
    """All fields optional — only the ones present are updated."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    plan: str | None = Field(default=None, max_length=32)
    box_quota: int | None = Field(default=None, ge=0, le=10_000)
    contact_email: str | None = Field(default=None, max_length=255)
    license_key: str | None = Field(default=None, max_length=255)
    license_expires: datetime | None = None


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ts: datetime
    tenant_id: UUID | None
    box_id: UUID | None
    actor: str
    event: str
    payload: dict | None


# -- Health ---------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str
