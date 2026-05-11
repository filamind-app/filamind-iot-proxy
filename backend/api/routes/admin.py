"""Admin read-only views for Phase 1.

Phase 4 will:
  * add auth (operator token)
  * add tenant CRUD
  * add box revoke / unpair
  * add cert listing
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_session
from api.models import Box, Tenant
from api.schemas import BoxOut, TenantOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/boxes", response_model=list[BoxOut])
async def list_boxes(session: AsyncSession = Depends(get_session)) -> list[BoxOut]:
    rows = (await session.scalars(select(Box).order_by(Box.created_at.desc()))).all()
    return [BoxOut.model_validate(r) for r in rows]


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(session: AsyncSession = Depends(get_session)) -> list[TenantOut]:
    rows = (await session.scalars(select(Tenant).order_by(Tenant.created_at.desc()))).all()
    return [TenantOut.model_validate(r) for r in rows]
