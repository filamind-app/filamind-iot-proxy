# Architecture notes

Deeper design for `filamind-iot-proxy` — a self-hosted clone of
`iot-proxy.odoo.com`'s public surface. Read [README.md](README.md) and
[REQUIREMENTS.md](REQUIREMENTS.md) first.

## Goal

Box-side code should switch from the upstream Odoo proxy to ours by
changing **one URL** and nothing else. We never modify the box's
core protocol assumptions; we only re-implement the server side.

## Endpoint surface — 1:1 with upstream

| Method | Path | Caller | Purpose |
|---|---|---|---|
| `POST` | `/odoo-enterprise/iot/connect-box` | box | rendezvous: get pairing code, poll for completion |
| `POST` | `/odoo-enterprise/iot/x509` | box | request fresh LE cert |
| `POST` | `/iot/finalize-pair` | customer's Odoo DB | bind a pairing code to a DB |
| `POST` | `/iot/box/<id>/heartbeat` | box | keepalive |
| `GET`  | `/iot/admin/tenants` | operator | list tenants (gated mode) |
| `POST` | `/iot/admin/tenant` | operator | create / update tenant |
| `GET`  | `/iot/admin/boxes` | operator | list boxes per tenant |
| `GET`  | `/healthz` | k8s / monitor | liveness |
| `GET`  | `/metrics` | Prometheus | aggregate metrics |

Reverse-tunnel paths:

| Path / port | Purpose |
|---|---|
| `:7000/tcp` | frps client connections (box → proxy) |
| `:7001/tcp` | frps dashboard (operator only, internal) |
| `https://<box-id>.tunnel.<your-domain>` | proxy → frps → box's nginx :443 |

## Database schema (Postgres 16)

```sql
CREATE TABLE tenant (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    license_key     TEXT,                          -- null = open mode
    license_expires TIMESTAMPTZ,
    contact_email   TEXT,
    plan            TEXT NOT NULL DEFAULT 'free',  -- free / starter / pro
    box_quota       INT  NOT NULL DEFAULT 5,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE box (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID REFERENCES tenant(id),    -- null until pairing finalised
    serial_number   TEXT NOT NULL UNIQUE,           -- pi serial / mac
    paired_db_uuid  TEXT,                           -- customer Odoo DB UUID
    paired_server_url TEXT,                         -- where the box phones home
    paired_at       TIMESTAMPTZ,
    last_seen       TIMESTAMPTZ,
    cert_subject    TEXT,                           -- *.<8hex>.box.<your-domain>
    cert_expires    TIMESTAMPTZ,
    tunnel_subdomain TEXT,                          -- assigned at first frpc connect
    box_token       TEXT,                           -- bearer for box → DB calls
    status          TEXT NOT NULL DEFAULT 'pending'  -- pending / active / suspended
);

CREATE TABLE pairing_code (
    code            TEXT PRIMARY KEY,               -- 8 chars, A-Z 0-9 (no I/O/0/1)
    box_id          UUID REFERENCES box(id),
    tenant_id       UUID REFERENCES tenant(id),     -- null until finalize
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    consumed_at     TIMESTAMPTZ,
    consumed_by_db_uuid TEXT
);

CREATE TABLE cert (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    box_id          UUID REFERENCES box(id) NOT NULL,
    pem             TEXT NOT NULL,
    private_key_pem TEXT NOT NULL,                  -- AES-256 encrypted at rest
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    issuer          TEXT NOT NULL DEFAULT 'lets-encrypt-r12',
    revoked_at      TIMESTAMPTZ
);

CREATE TABLE audit (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    tenant_id       UUID REFERENCES tenant(id),
    box_id          UUID REFERENCES box(id),
    actor           TEXT,                           -- 'box' / 'admin' / 'odoo-db'
    event           TEXT NOT NULL,                  -- pair / unpair / cert.issue / ...
    payload         JSONB
);

CREATE INDEX box_serial_idx       ON box (serial_number);
CREATE INDEX box_tenant_idx       ON box (tenant_id, status);
CREATE INDEX cert_box_idx         ON cert (box_id, expires_at DESC);
CREATE INDEX audit_ts_idx         ON audit (ts DESC);
CREATE INDEX pairing_expires_idx  ON pairing_code (expires_at)
    WHERE consumed_at IS NULL;
```

## Pairing flow (sequence)

```
┌──────┐                ┌────────────┐               ┌──────────────┐
│ Box  │                │ Proxy API  │               │ Customer DB  │
└──┬───┘                └─────┬──────┘               └──────┬───────┘
   │ POST /connect-box        │                             │
   │ {serial_number}          │                             │
   ├─────────────────────────>│                             │
   │                          │  INSERT box(serial)         │
   │                          │  INSERT pairing_code        │
   │ {pairing_code, uuid}     │                             │
   │<─────────────────────────┤                             │
   │ display HDMI + poll      │                             │
   │ every 14s                │                             │
   ├─────────────────────────>│ (no consumed_at yet)        │
   │ {status: 'waiting'}      │                             │
   │<─────────────────────────┤                             │
   │                          │                             │
   │                          │      User enters code in    │
   │                          │      DB IoT app             │
   │                          │  POST /iot/finalize-pair    │
   │                          │  {code, db_uuid, server_url}│
   │                          │<────────────────────────────┤
   │                          │  validate code, license     │
   │                          │  set consumed_at + tenant   │
   │                          │  generate box_token         │
   │                          │  {ok: true}                 │
   │                          ├────────────────────────────>│
   │ POST /connect-box (poll) │                             │
   ├─────────────────────────>│                             │
   │ {url, token, db_uuid,    │                             │
   │  enterprise_code}        │                             │
   │<─────────────────────────┤                             │
   │ persist [iot.box]        │                             │
   │ → restart                │                             │
```

## Cert issuance (sequence)

```
┌──────┐                ┌────────────┐               ┌──────────────┐
│ Box  │                │ Proxy API  │               │ DNS Provider │
└──┬───┘                └─────┬──────┘               └──────┬───────┘
   │ POST /x509               │                             │
   │ {db_uuid, ent_code,      │                             │
   │  identifier}             │                             │
   ├─────────────────────────>│                             │
   │                          │ validate license            │
   │                          │ pick subdomain: 8hex+box.X  │
   │                          │ lego --dns cloudflare order │
   │                          │  for *.<8hex>.box.X         │
   │                          │  ─ TXT _acme-challenge ───────>│
   │                          │  ─ wait propagation ──────────│
   │                          │  ─ poll DNS ─────────────────>│
   │                          │  ─ submit to LE ──── (real LE)
   │                          │  ─ download fullchain.pem    │
   │                          │ INSERT cert(...)            │
   │ {x509_pem, key_pem,      │                             │
   │  subject_cn}             │                             │
   │<─────────────────────────┤                             │
   │ install on nginx         │                             │
   │ POST DB.update_cert_status                             │
```

## Reverse-tunnel flow (frp)

```
┌──────┐ frpc            ┌────────────┐ frps              ┌────────┐
│ Box  │ ─ persistent ─> │ Proxy host │  ─ subdomain ───> │ Public │
│      │   TCP :7000     │            │   <id>.tunnel.X   │ DNS    │
└──────┘                 └────────────┘                   └────────┘
   ▲ box's nginx :443                ▲
   │                                 │
   │ tunnel multiplexed              │ HTTPS terminator
   │ inside the frpc/frps connection │ presents box's LE cert
                                     │ to incoming browser request
                                     │
                              ┌──────┴──────┐
                              │ POS browser │
                              │ in customer │
                              │    LAN      │
                              └─────────────┘
```

The customer's POS browser hits `https://<box-id>.tunnel.your-domain`,
the proxy's HTTPS layer terminates with the box's own LE cert (forwarded
through the tunnel), and the request body is shipped to the box's
nginx over the persistent frp connection. From the browser's
perspective, it's talking directly to the box; from the box's
perspective, it's serving local nginx.

## Security model

1. **No long-lived secrets stored in the box.** The proxy returns a
   per-pair `box_token` to the box; the box uses that with the
   customer's DB. The proxy never sees actual customer DB data.

2. **Cert private keys at rest.** `cert.private_key_pem` AES-256
   encrypted in Postgres with a key derived from `PROXY_MASTER_KEY`
   env var (rotated quarterly).

3. **Pairing codes are single-use + 2h TTL.** Reduces window for
   guessing attacks (8-char alphanumeric ≈ 2.8 trillion possibilities,
   but TTL stops bulk grinding).

4. **License keys signed.** Tenant `license_key` is a JWT signed by
   the operator's private key. Box-side validation needs only the
   public key.

5. **No POS / payment data ever flows through the proxy.** The proxy
   is a control-plane service; POS data flows directly box ↔ DB once
   pairing completes. Reduces PCI-DSS scope.

## Operational concerns

- **Cert renewal cron**: every 6h, find certs with `expires_at < now()
  + 30d`, reissue. Push to box via WebSocket announcement.
- **Box-down detection**: `last_seen < now() - 5m`. Notify operator
  via configured channel.
- **Pairing-code GC**: hourly, delete `WHERE expires_at < now() - 24h
  AND consumed_at IS NULL`.
- **frp tunnel auth**: per-box `frpc.toml` with unique token, signed
  by the proxy at first cert issue.

## Migration paths

- **Existing boxes on `iot-proxy.odoo.com`**: change one config line
  in the box, re-pair, done. The Odoo cert keeps working until expiry
  (~90d), giving plenty of cutover time.
- **Future move to dedicated VPS**: same Docker compose, same DNS,
  swap the A record. Postgres dump + restore. Boxes notice nothing.
