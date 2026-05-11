# ACME (Let's Encrypt via Cloudflare DNS-01) — Phase 2

This is the operator runbook for issuing per-box LE certs through the
proxy.

> **Status:** the wiring is in place; the endpoint returns 503
> `acme_not_configured` until the operator supplies the three required
> env vars below.

---

## Prerequisites

1. A DNS zone you control on Cloudflare (e.g. `box.filamind.app`).
2. A scoped Cloudflare API token with `Zone:DNS:Edit` on **only** that
   zone (REQUIREMENTS.md §2 — never account-level).
3. `lego` installed in the api container (already shipped via
   `Dockerfile`'s `LEGO_VERSION` build arg).

---

## Bring-up

1. Edit `.env`:

   ```
   CLOUDFLARE_DNS_API_TOKEN=<your-zone-scoped-token>
   CERT_BASE_DOMAIN=box.filamind.app
   ACME_EMAIL=ops@filamind.app
   ```

2. Restart the api container so the new env is picked up:

   ```bash
   docker compose up -d proxy-api
   ```

3. Verify the gate flipped:

   ```bash
   curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
     -X POST http://localhost:9100/admin/boxes/<box-id>/issue_cert
   # Expect 200 + a BoxOut with cert_subject populated, NOT 503.
   ```

   The first call may take 60–120 s because lego must:
   * register an LE account (only on first call ever),
   * create the `_acme-challenge` TXT record on Cloudflare,
   * wait for DNS propagation,
   * complete the DNS-01 challenge,
   * fetch the cert from LE.

4. Cert and key live under `./data/acme/certificates/<short-id>.<base>.{crt,key}`.

---

## Renewal

Phase 2 ships **manual** renewal. From a host crontab:

```
0 4 * * * docker compose -f /opt/filamind-iot-proxy/docker-compose.yml \
    exec -T proxy-api lego \
        --accept-tos --email ops@filamind.app --dns cloudflare \
        --path /var/lib/proxy/acme renew --days 30
```

Auto-renewal as a background scheduler is a Phase 7 hardening item.

---

## Revocation

```bash
docker compose exec proxy-api lego \
    --accept-tos --email ops@filamind.app --dns cloudflare \
    --path /var/lib/proxy/acme revoke --domains <subject>
```

After revocation, mark the row revoked from the admin Odoo addon
(Phase 4b — TODO: a `Revoke` button on the cert form lands when
`/admin/certs/{id}/revoke` is added).

---

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| 503 `acme_not_configured` | One or more env vars unset | Set all three in `.env`, `docker compose up -d proxy-api` |
| 502 `lego_run_failed: ...` | CF token wrong scope, propagation timeout, rate-limit | Check `docker compose logs proxy-api`; the lego stderr is included in the message |
| 502 `lego_outputs_missing` | lego succeeded but wrote to a different path | Check `ACME_STORAGE_PATH` env matches volume mount |
| `502` repeatedly with rate-limit error | Hit LE's prod rate limit (5 dupes/week) | Switch to staging by adding `--server https://acme-staging-v02.api.letsencrypt.org/directory` to the lego call (TODO: env-toggle in `services/acme.py`) |

---

## Why Cloudflare DNS-01

* **No port-80 challenge** required — boxes behind NAT don't need to
  expose anything for cert issuance.
* **Wildcard support** — `*.tunnel.<base>` is a single cert covering
  every reverse-tunnel subdomain.
* **Automatable** — `lego` + token = zero manual steps after env is
  filled in.

The trade-off: API token compromise = full DNS control over the zone.
Hence the strict `Zone:DNS:Edit` scope and quarterly rotation in
REQUIREMENTS.md §2.
