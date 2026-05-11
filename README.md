# filamind-iot-proxy

Self-hosted IoT-Box pairing rendezvous + ACME cert issuer + reverse-tunnel
relay. The **LGPL-3 alternative to `iot-proxy.odoo.com`** — exposes the
same protocol surface boxes already speak, but runs on your own server.

Pairs with [`filamind-iot`](https://github.com/filamind-app/filamind-iot)
(server-side Odoo addons) and
[`filamind-iotbox`](https://github.com/filamind-app/filamind-iotbox)
(Raspberry-Pi IoT Box image).

> Status: **scaffold only — not yet implemented.** See
> [ROADMAP.md](ROADMAP.md) for the full delivery plan, and
> [REQUIREMENTS.md](REQUIREMENTS.md) for the inputs needed to start
> implementation.

## What it does

1. **Pairing rendezvous** — boxes phone home (`POST /iot/connect-box`)
   and get a pairing code. The user enters the code in their Odoo DB.
   When the user's DB calls `POST /iot/finalize-pair` with the same
   code, the box's next poll returns `{url, token, db_uuid}`. Same
   protocol shape as `iot-proxy.odoo.com`.

2. **ACME cert issuance** — boxes request `POST /iot/x509`. The proxy
   holds a Let's Encrypt account, runs DNS-01 against a managed
   wildcard zone (e.g. `*.box.<your-domain>`), and returns the PEM +
   private key. Per-box subdomain like `<8hex>.box.<your-domain>`.

3. **Reverse-tunnel relay (optional)** — boxes behind NAT open a
   persistent outbound connection (frp client → frps server) and
   become reachable from the public internet at
   `https://<box-subdomain>.<your-domain>`. The customer's POS browser
   can hit them with a clean cert; no LAN access required.

4. **License / subscription gate (optional)** — turn it on and the
   proxy refuses pairing + cert issuance for unknown / expired tenants.
   Turn it off and the proxy is permissive (default).

## Architecture

```
                        +----------------------------+
                        |   iot-proxy.<your-domain>   |
                        +----------------------------+
                        |  proxy-api (FastAPI :9100) |
                        |  proxy-db  (Postgres 16)   |
                        |  proxy-redis (pair codes)  |
                        |  proxy-acme (lego DNS-01)  |
                        |  proxy-frps (port 7000)    |
                        |  proxy-caddy (TLS termin.) |
                        +----------------------------+
                                   ▲
                        same HTTP surface as
                       iot-proxy.odoo.com
                                   │
                ┌──────────────────┼──────────────────┐
                │                  │                  │
            ┌───┴───┐          ┌───┴───┐          ┌───┴───┐
            │ Box A │          │ Box B │          │ Box C │
            └───┬───┘          └───┬───┘          └───┬───┘
                │ paired DB        │ paired DB        │ paired DB
                ▼                  ▼                  ▼
          Customer Odoo     Customer Odoo      Customer Odoo
```

## Stack

| Component | Tech | Notes |
|---|---|---|
| Pairing API | Python 3.12 + FastAPI | shipped as Docker image |
| Database | PostgreSQL 16 | tenants, boxes, certs, audit log |
| Pair-code store | Redis 7 | TTL-based, ephemeral |
| TLS termination | Caddy 2 | automatic ACME for the proxy itself |
| ACME (per-box certs) | [lego](https://github.com/go-acme/lego) | DNS-01 via Cloudflare API |
| Reverse tunnel | [frp](https://github.com/fatedier/frp) | frps server + per-box frpc |
| Deploy | Docker Compose (single host) | k8s manifests later if needed |
| Monitoring | Prometheus + Grafana | cert-expiry alerts, box heartbeats |

## Compatibility with the upstream protocol

The box-facing endpoint shapes mirror `iot-proxy.odoo.com` exactly so a
**single env var change in the box** is enough to switch a fleet from
Odoo's proxy to a self-hosted one:

```ini
# /home/pi/odoo.conf  [iot.box]
proxy_url = https://iot-proxy.<your-domain>     # default: https://iot-proxy.odoo.com
```

See [`filamind-iotbox` PR #N](https://github.com/filamind-app/filamind-iotbox)
(forthcoming) — patch 009 makes the proxy URL configurable in the
homepage UI, defaulting to upstream when blank.

## Quick deploy (after implementation lands)

```bash
git clone https://github.com/filamind-app/filamind-iot-proxy
cd filamind-iot-proxy
cp .env.example .env
# Fill .env — domain, Cloudflare API token, Postgres password, etc.
docker compose up -d
```

Three DNS records and the proxy is alive (see REQUIREMENTS.md §3).

## License

LGPL-3.0-or-later — same as `filamind-iot` and `filamind-iotbox`.

## Repo state

```
[scaffold]
├── README.md            ← you are here
├── ROADMAP.md           ← phased delivery plan, conventions, decisions
├── REQUIREMENTS.md      ← what we need from the operator before building
├── ARCHITECTURE.md      ← deeper design notes (schema, sequences)
├── docker-compose.yml   ← (todo, Phase 1)
├── backend/             ← (todo, Phase 1) FastAPI source
├── caddy/Caddyfile      ← (todo, Phase 7)
├── frps/frps.toml       ← (todo, Phase 3)
└── docs/                ← (todo, Phase 7) operator + customer guides
```

**For the full delivery plan, file-level scope of every PR, decisions
locked-in, decisions pending, conventions, migration paths, and
acceptance criteria — see [ROADMAP.md](ROADMAP.md).**

Tracking issue: [filamind-iot-proxy #1](https://github.com/filamind-app/filamind-iot-proxy/issues/1)
(forthcoming).
