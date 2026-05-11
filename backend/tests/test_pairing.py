"""End-to-end pairing flow tests."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_ok(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_connect_returns_pairing_code(client):
    r = await client.post(
        "/iot/connect",
        json={"serial_number": "PI-12345678"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "pairing_code" in body
    assert "box_id" in body
    assert len(body["pairing_code"]) >= 4


@pytest.mark.asyncio
async def test_connect_is_idempotent_per_serial(client):
    r1 = await client.post("/iot/connect", json={"serial_number": "PI-X"})
    r2 = await client.post("/iot/connect", json={"serial_number": "PI-X"})
    assert r1.status_code == r2.status_code == 200
    # Same box, fresh code each time
    assert r1.json()["box_id"] == r2.json()["box_id"]
    assert r1.json()["pairing_code"] != r2.json()["pairing_code"]


@pytest.mark.asyncio
async def test_poll_unknown_code(client):
    r = await client.get("/iot/poll/NOPE0000")
    assert r.status_code == 200
    assert r.json()["status"] == "unknown"


@pytest.mark.asyncio
async def test_poll_pending_then_consumed(client):
    connect = await client.post(
        "/iot/connect", json={"serial_number": "PI-Y"},
    )
    code = connect.json()["pairing_code"]

    poll1 = await client.get(f"/iot/poll/{code}")
    assert poll1.json()["status"] == "pending"

    finalize = await client.post(
        "/iot/finalize",
        json={
            "code": code,
            "db_uuid": "abc-123-db",
            "server_url": "https://customer.example.com",
        },
    )
    assert finalize.status_code == 200, finalize.text

    poll2 = await client.get(f"/iot/poll/{code}")
    body = poll2.json()
    assert body["status"] == "consumed"
    assert body["paired_db_uuid"] == "abc-123-db"
    assert body["paired_server_url"] == "https://customer.example.com"


@pytest.mark.asyncio
async def test_finalize_unknown_code_409(client):
    r = await client.post(
        "/iot/finalize",
        json={
            "code": "NOTREAL1",
            "db_uuid": "x" * 16,
            "server_url": "https://example.com",
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "unknown_code"


@pytest.mark.asyncio
async def test_finalize_twice_409(client):
    connect = await client.post("/iot/connect", json={"serial_number": "PI-Z"})
    code = connect.json()["pairing_code"]

    body = {
        "code": code,
        "db_uuid": "first-db-uuid",
        "server_url": "https://first.example.com",
    }
    ok = await client.post("/iot/finalize", json=body)
    assert ok.status_code == 200

    second = await client.post(
        "/iot/finalize", json={**body, "db_uuid": "second-db-uuid"},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "already_consumed"


@pytest.mark.asyncio
async def test_admin_lists_paired_box(client):
    await client.post("/iot/connect", json={"serial_number": "PI-ADMIN-1"})
    r = await client.get("/admin/boxes")
    assert r.status_code == 200
    serials = [b["serial_number"] for b in r.json()]
    assert "PI-ADMIN-1" in serials
