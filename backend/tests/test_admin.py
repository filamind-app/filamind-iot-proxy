"""Admin endpoint tests — auth gate, tenant CRUD, box unpair, audit log."""
from __future__ import annotations

import os

import pytest

ADMIN_TOKEN = "test-admin-token-please-rotate"
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@pytest.fixture(autouse=True)
def _set_admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_TOKEN)
    # Settings is lru_cached — clear so we re-read
    from api.config import get_settings
    get_settings.cache_clear()
    yield
    os.environ.pop("ADMIN_TOKEN", None)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_admin_requires_bearer(client):
    r = await client.get("/admin/boxes")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer"


@pytest.mark.asyncio
async def test_admin_rejects_wrong_token(client):
    r = await client.get(
        "/admin/boxes", headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "invalid_token"


@pytest.mark.asyncio
async def test_503_when_admin_token_unset(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "")
    from api.config import get_settings
    get_settings.cache_clear()
    r = await client.get("/admin/boxes", headers=HEADERS)
    assert r.status_code == 503
    assert r.json()["detail"] == "admin_token_not_configured"


@pytest.mark.asyncio
async def test_tenant_crud_roundtrip(client):
    create = await client.post(
        "/admin/tenants",
        headers=HEADERS,
        json={"name": "Acme Coffee", "plan": "pro", "box_quota": 25},
    )
    assert create.status_code == 201, create.text
    tenant_id = create.json()["id"]
    assert create.json()["box_quota"] == 25

    fetched = await client.get(f"/admin/tenants/{tenant_id}", headers=HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Acme Coffee"

    patched = await client.patch(
        f"/admin/tenants/{tenant_id}",
        headers=HEADERS,
        json={"box_quota": 100, "contact_email": "ops@acme.test"},
    )
    assert patched.status_code == 200
    assert patched.json()["box_quota"] == 100
    assert patched.json()["contact_email"] == "ops@acme.test"
    # Unchanged field preserved
    assert patched.json()["plan"] == "pro"

    deleted = await client.delete(
        f"/admin/tenants/{tenant_id}", headers=HEADERS,
    )
    assert deleted.status_code == 204

    missing = await client.get(f"/admin/tenants/{tenant_id}", headers=HEADERS)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_unpair_box_clears_pairing(client):
    connect = await client.post("/iot/connect", json={"serial_number": "PI-UNPAIR"})
    box_id = connect.json()["box_id"]
    code = connect.json()["pairing_code"]
    await client.post(
        "/iot/finalize",
        json={
            "code": code,
            "db_uuid": "the-db-uuid-1",
            "server_url": "https://x.example.com",
        },
    )

    before = await client.get(f"/admin/boxes/{box_id}", headers=HEADERS)
    assert before.json()["status"] == "paired"
    assert before.json()["paired_db_uuid"] == "the-db-uuid-1"

    unpair = await client.post(f"/admin/boxes/{box_id}/unpair", headers=HEADERS)
    assert unpair.status_code == 200
    assert unpair.json()["status"] == "pending"
    assert unpair.json()["paired_db_uuid"] is None
    assert unpair.json()["paired_at"] is None


@pytest.mark.asyncio
async def test_audit_log_records_pairing_events(client):
    await client.post("/iot/connect", json={"serial_number": "PI-AUDIT"})
    audit = await client.get("/admin/audit", headers=HEADERS)
    assert audit.status_code == 200
    events = [a["event"] for a in audit.json()]
    assert "connect" in events


@pytest.mark.asyncio
async def test_delete_tenant_with_boxes_blocks(client, session):
    # Create a tenant via the API
    create = await client.post(
        "/admin/tenants", headers=HEADERS, json={"name": "Has Boxes"},
    )
    tenant_id = create.json()["id"]

    # Manually attach a box to that tenant
    from uuid import UUID as _UUID

    from api.models import Box
    box = Box(
        serial_number="PI-OWNED",
        tenant_id=_UUID(tenant_id),
        status="pending",
    )
    session.add(box)
    await session.commit()

    blocked = await client.delete(
        f"/admin/tenants/{tenant_id}", headers=HEADERS,
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"].startswith("tenant_has_boxes")
