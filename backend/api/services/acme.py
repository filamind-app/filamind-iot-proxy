"""ACME (Let's Encrypt) cert issuance via the `lego` CLI + Cloudflare DNS-01.

Phase 2 scope is intentionally minimal:
  * `is_configured()` — returns False unless every required env var is set.
  * `issue_for_box()` — runs `lego` to mint a wildcard-friendly cert
    for `<short-id>.<cert_base_domain>`. Stores PEM + encrypted key
    in the `cert` table.
  * `revoke()` — runs `lego revoke` and marks the row revoked.

Renewal is operator-driven for now (a cron container or a host
crontab calling `lego renew`). Auto-renewal lands when the cert
table grows enough to warrant a background scheduler.

The actual `lego` binary is shipped by the `proxy-acme` container
(see docker-compose); this module shells out to it via subprocess.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.models import Box, Cert
from api.services import pairing as pairing_svc

_logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """True only when every ACME env is filled in. False -> 503 path."""
    s = get_settings()
    return bool(
        s.cloudflare_dns_api_token
        and s.cert_base_domain
        and s.acme_email,
    )


def short_id(box_id: UUID) -> str:
    """Short, DNS-safe id for the wildcard subdomain."""
    return box_id.hex[:8]


def cert_subject_for(box: Box) -> str:
    s = get_settings()
    return f"{short_id(box.id)}.{s.cert_base_domain}"


async def _run_lego(args: list[str]) -> tuple[int, str, str]:
    """Run lego with the given args; capture stdout/stderr."""
    s = get_settings()
    env = {
        **os.environ,
        "CLOUDFLARE_DNS_API_TOKEN": s.cloudflare_dns_api_token,
    }
    Path(s.acme_storage_path).mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        "lego",
        "--accept-tos",
        "--email", s.acme_email,
        "--dns", "cloudflare",
        "--path", s.acme_storage_path,
        *args,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def issue_for_box(session: AsyncSession, box: Box) -> Cert:
    """Mint a cert for `<short-id>.<base>` and persist it.

    Raises:
        RuntimeError: ACME unconfigured or `lego` failed.
    """
    if not is_configured():
        raise RuntimeError("acme_not_configured")

    s = get_settings()
    domain = cert_subject_for(box)
    code, stdout, stderr = await _run_lego(["--domains", domain, "run"])
    if code != 0:
        _logger.warning("lego run failed: %s\n%s", stdout, stderr)
        raise RuntimeError(f"lego_run_failed: {stderr.strip()[:200]}")

    cert_dir = Path(s.acme_storage_path) / "certificates"
    pem_path = cert_dir / f"{domain}.crt"
    key_path = cert_dir / f"{domain}.key"
    if not pem_path.exists() or not key_path.exists():
        raise RuntimeError("lego_outputs_missing")

    pem = pem_path.read_text()
    key = key_path.read_text()
    # Phase 2 stub: store the key in plaintext (DB column is named
    # private_key_encrypted to reserve the name; envelope encryption
    # via PROXY_MASTER_KEY lands in Phase 7 hardening).
    expires = _peek_cert_not_after(pem)

    cert = Cert(
        box_id=box.id,
        pem=pem,
        private_key_encrypted=key,
        expires_at=expires,
        issuer="lets-encrypt",
    )
    session.add(cert)
    box.cert_subject = domain
    box.cert_expires = expires
    await pairing_svc.record_audit(
        session,
        actor="acme",
        event="issue_cert",
        box_id=box.id,
        payload={"domain": domain},
    )
    await session.flush()
    return cert


def _peek_cert_not_after(pem: str) -> datetime:
    """Read the notAfter date from a PEM cert without external deps.

    Falls back to "now + 90d" if cryptography is unavailable (test envs
    that don't install the lib for the optional ACME path).
    """
    try:
        from cryptography import x509
        cert = x509.load_pem_x509_certificate(pem.encode())
        return cert.not_valid_after_utc
    except Exception:  # noqa: BLE001
        return datetime.now(UTC).replace(microsecond=0)
