"""ACME endpoint tests — only the un-configured path is exercised here.

Live cert issuance against Let's Encrypt staging is out of scope for
unit tests; the full happy-path is covered by an operator runbook in
docs/ACME.md.
"""
from __future__ import annotations

import os
from uuid import UUID

import pytest

ADMIN_TOKEN = "test-admin-token-please-rotate"
HEADERS = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@pytest.fixture(autouse=True)
def _set_admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_TOKEN)
    # Ensure ACME envs are unset so the un-configured path is the
    # default for every test in this file.
    for var in ("CLOUDFLARE_DNS_API_TOKEN", "CERT_BASE_DOMAIN", "ACME_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    from api.config import get_settings
    get_settings.cache_clear()
    yield
    os.environ.pop("ADMIN_TOKEN", None)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_issue_cert_503_when_acme_not_configured(client):
    connect = await client.post("/iot/connect", json={"serial_number": "PI-CERT"})
    box_id = connect.json()["box_id"]

    r = await client.post(
        f"/admin/boxes/{box_id}/issue_cert", headers=HEADERS,
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "acme_not_configured"


@pytest.mark.asyncio
async def test_issue_cert_503_even_with_partial_config(client, monkeypatch):
    # Only one of the three is set — service must still return 503.
    monkeypatch.setenv("CLOUDFLARE_DNS_API_TOKEN", "fake")
    from api.config import get_settings
    get_settings.cache_clear()

    connect = await client.post("/iot/connect", json={"serial_number": "PI-PARTIAL"})
    box_id = connect.json()["box_id"]

    r = await client.post(
        f"/admin/boxes/{box_id}/issue_cert", headers=HEADERS,
    )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_acme_is_configured_helper(monkeypatch):
    from api.config import get_settings
    from api.services import acme

    # All unset
    get_settings.cache_clear()
    assert acme.is_configured() is False

    # Two of three set
    monkeypatch.setenv("CLOUDFLARE_DNS_API_TOKEN", "tok")
    monkeypatch.setenv("CERT_BASE_DOMAIN", "box.example.com")
    get_settings.cache_clear()
    assert acme.is_configured() is False

    # All three
    monkeypatch.setenv("ACME_EMAIL", "ops@example.com")
    get_settings.cache_clear()
    assert acme.is_configured() is True


@pytest.mark.asyncio
async def test_short_id_helper():
    from api.services import acme
    bid = UUID("12345678-1234-1234-1234-123456789012")
    assert acme.short_id(bid) == "12345678"


@pytest.mark.asyncio
async def test_issue_cert_404_for_unknown_box(client, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_DNS_API_TOKEN", "tok")
    monkeypatch.setenv("CERT_BASE_DOMAIN", "box.example.com")
    monkeypatch.setenv("ACME_EMAIL", "ops@example.com")
    from api.config import get_settings
    get_settings.cache_clear()

    r = await client.post(
        "/admin/boxes/00000000-0000-0000-0000-000000000000/issue_cert",
        headers=HEADERS,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "box_not_found"
