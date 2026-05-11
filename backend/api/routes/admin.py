"""Operator admin endpoints (bearer-token auth).

Phase 4a scope:
  GET    /admin/boxes                    list (paginated)
  GET    /admin/boxes/{id}               detail
  POST   /admin/boxes/{id}/unpair        clear pairing, revert to 'pending'

  GET    /admin/tenants                  list
  POST   /admin/tenants                  create
  GET    /admin/tenants/{id}             detail
  PATCH  /admin/tenants/{id}             partial update
  DELETE /admin/tenants/{id}             hard delete (only if no boxes)

  GET    /admin/audit                    paginated audit log

Cert listing + revoke land in Phase 2 alongside ACME.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db import get_session
from api.models import Audit, Box, Tenant
from api.schemas import (
    AuditOut,
    BoxOut,
    TenantCreate,
    TenantOut,
    TenantPatch,
)
from api.security import require_admin
from api.services import pairing as svc

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


# -- Boxes ----------------------------------------------------------------

@router.get("/boxes", response_model=list[BoxOut])
async def list_boxes(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tenant_id: UUID | None = Query(default=None),
    status_eq: str | None = Query(default=None, alias="status"),
) -> list[BoxOut]:
    stmt = select(Box).order_by(Box.created_at.desc()).limit(limit).offset(offset)
    if tenant_id is not None:
        stmt = stmt.where(Box.tenant_id == tenant_id)
    if status_eq is not None:
        stmt = stmt.where(Box.status == status_eq)
    rows = (await session.scalars(stmt)).all()
    return [BoxOut.model_validate(r) for r in rows]


@router.get("/boxes/{box_id}", response_model=BoxOut)
async def get_box(box_id: UUID, session: AsyncSession = Depends(get_session)) -> BoxOut:
    box = await session.get(Box, box_id)
    if box is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "box_not_found")
    return BoxOut.model_validate(box)


@router.post("/boxes/{box_id}/unpair", response_model=BoxOut)
async def unpair_box(
    box_id: UUID, session: AsyncSession = Depends(get_session),
) -> BoxOut:
    box = await session.get(Box, box_id)
    if box is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "box_not_found")
    box.paired_db_uuid = None
    box.paired_server_url = None
    box.paired_at = None
    box.status = "pending"
    await svc.record_audit(
        session,
        actor="admin",
        event="unpair",
        box_id=box.id,
        tenant_id=box.tenant_id,
    )
    await session.commit()
    await session.refresh(box)
    return BoxOut.model_validate(box)


# -- Tenants --------------------------------------------------------------

@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[TenantOut]:
    stmt = select(Tenant).order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.scalars(stmt)).all()
    return [TenantOut.model_validate(r) for r in rows]


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate, session: AsyncSession = Depends(get_session),
) -> TenantOut:
    tenant = Tenant(
        name=body.name,
        plan=body.plan,
        box_quota=body.box_quota,
        contact_email=body.contact_email,
        license_key=body.license_key,
        license_expires=body.license_expires,
    )
    session.add(tenant)
    await session.flush()
    await svc.record_audit(
        session, actor="admin", event="tenant_create", tenant_id=tenant.id,
        payload={"name": body.name, "plan": body.plan},
    )
    await session.commit()
    await session.refresh(tenant)
    return TenantOut.model_validate(tenant)


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
async def get_tenant(
    tenant_id: UUID, session: AsyncSession = Depends(get_session),
) -> TenantOut:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant_not_found")
    return TenantOut.model_validate(tenant)


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
async def patch_tenant(
    tenant_id: UUID,
    body: TenantPatch,
    session: AsyncSession = Depends(get_session),
) -> TenantOut:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant_not_found")
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(tenant, key, value)
    await svc.record_audit(
        session, actor="admin", event="tenant_patch", tenant_id=tenant.id,
        payload={"changed": list(updates.keys())},
    )
    await session.commit()
    await session.refresh(tenant)
    return TenantOut.model_validate(tenant)


@router.delete("/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: UUID, session: AsyncSession = Depends(get_session),
) -> None:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant_not_found")
    box_count = await session.scalar(
        select(func.count()).select_from(Box).where(Box.tenant_id == tenant_id),
    )
    if box_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"tenant_has_boxes: {box_count}",
        )
    await session.delete(tenant)
    await svc.record_audit(
        session, actor="admin", event="tenant_delete", tenant_id=tenant_id,
    )
    await session.commit()


# -- Audit ----------------------------------------------------------------

@router.get("/audit", response_model=list[AuditOut])
async def list_audit(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    box_id: UUID | None = Query(default=None),
    tenant_id: UUID | None = Query(default=None),
    event: str | None = Query(default=None),
) -> list[AuditOut]:
    stmt = select(Audit).order_by(Audit.id.desc()).limit(limit).offset(offset)
    if box_id is not None:
        stmt = stmt.where(Audit.box_id == box_id)
    if tenant_id is not None:
        stmt = stmt.where(Audit.tenant_id == tenant_id)
    if event is not None:
        stmt = stmt.where(Audit.event == event)
    rows = (await session.scalars(stmt)).all()
    return [AuditOut.model_validate(r) for r in rows]
