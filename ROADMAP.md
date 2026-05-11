# filamind IoT Proxy + ecosystem roadmap

Single source of truth for the multi-repo effort to ship a self-hosted
alternative to `iot-proxy.odoo.com`. Designed so any future contributor
(human or AI) can pick up exactly where we left off without re-deriving
context.

**Last updated**: by Claude Opus 4.7 session 7c278097, on 2026-05-11.
**Owner**: [eg2](https://github.com/...)

---

## 1. Vision

A self-hosted IoT-Box pairing rendezvous + ACME cert issuer + reverse-
tunnel relay. Boxes switch from upstream Odoo proxy to our own with a
single config change. LGPL-3, no Enterprise subscription, no vendor
lock-in.

## 2. Three repos involved

| Repo | Role | License |
|---|---|---|
| **filamind-iot-proxy** (NEW) | FastAPI standalone service hosting pairing + cert + tunnel APIs | LGPL-3 |
| **filamind-iot** (existing) | Odoo addons. New addon `filamind_iot_proxy_admin` is a **thin REST client** giving operators an Odoo-native UI to manage the proxy | LGPL-3 |
| **filamind-iotbox** (existing) | Pi image patches. **patch 009** makes the box's proxy URL configurable — switch from upstream Odoo to our proxy via box's homepage UI | LGPL-3 |

## 3. Decisions locked-in

| Decision | Value | Made when |
|---|---|---|
| Proxy hostname | `iot-proxy.filamind.app` | session 7c278097 |
| Wildcard cert zone | `*.box.filamind.app` | session 7c278097 |
| DNS provider | Cloudflare (operator owns all domains there) | session 7c278097 |
| Hosting (MVP) | Existing customer server `157.90.152.154` | session 7c278097 |
| Hosting (production-ready) | Hetzner CX22 €4.51/mo (deferred) | proposed |
| License model | **Open** — no subscription gate | session 7c278097 |
| Reverse tunnel | **Yes** — frp from day one | session 7c278097 |
| Source visibility | **Public LGPL-3** for all 3 repos | session 7c278097 |
| Architecture flavor | **Thin** — FastAPI standalone + thin Odoo addon | session 7c278097 |
| Backend stack | Python 3.12 + FastAPI + Pydantic v2 | architecture choice |
| DB | PostgreSQL 16 (separate from Odoo's) | architecture choice |
| Pair-code store | Redis 7 | architecture choice |
| TLS termination | Caddy 2 (auto ACME for proxy itself) | architecture choice |
| ACME client (per-box) | `lego` Go binary (DNS-01 Cloudflare) | architecture choice |
| Reverse tunnel | `frp` (frps server + frpc per box) | architecture choice |
| Container orchestration | Docker Compose (single host MVP) | architecture choice |

## 4. Decisions pending

| Decision | Blocked on | Required by |
|---|---|---|
| Cloudflare API token (zone-scoped) | Operator generates + shares securely | Phase 2 |
| Brand UI name + logo | Operator | Phase 4 |
| SMTP / Slack notifications | Operator | Phase 6 |
| Migration to dedicated VPS | Operator decision (after MVP works) | Phase 7 |
| License keys / billing model | Operator decision (only if going gated) | Phase 8 (optional) |

---

## 5. Phased delivery

Each phase = one PR. PRs are atomic, tested, mergeable independently.
**Branch protection on `main` requires all CI green; no direct pushes.**

### Phase 0: Repo + CI bootstrap ✅ DONE

Already merged. Repo structure, CI workflow, branch protection.

### Phase 1: Pairing API + DB schema + Docker Compose 🚧 NEXT

**Repo**: filamind-iot-proxy
**PR title**: `feat: phase 1 — pairing API + DB schema + docker compose`
**Branch**: `feat/phase-1-pairing-api`
**CF token required**: NO

**Files to create**:
```
docker-compose.yml                         # postgres + redis + api
.env.example                               # all env vars documented
Dockerfile                                 # backend image
backend/pyproject.toml                     # FastAPI + sqlalchemy + alembic + pydantic v2 + redis-py
backend/alembic.ini
backend/alembic/env.py
backend/alembic/versions/0001_initial.py   # tenant, box, pairing_code, cert, audit
backend/api/__init__.py
backend/api/app.py                         # FastAPI app + lifespan
backend/api/config.py                      # pydantic-settings env reader
backend/api/db.py                          # async SQLAlchemy engine + session
backend/api/models.py                      # SQLAlchemy ORM
backend/api/schemas.py                     # pydantic request/response
backend/api/routes/health.py               # /healthz, /readyz
backend/api/routes/pairing.py              # POST /odoo-enterprise/iot/connect-box
                                           # POST /iot/finalize-pair
backend/api/routes/admin.py                # GET /admin/tenants, /admin/boxes (no auth yet)
backend/api/services/pairing.py            # business logic
backend/tests/__init__.py
backend/tests/conftest.py                  # pytest fixtures (in-memory db)
backend/tests/test_pairing.py              # full pairing flow
```

**Acceptance criteria**:
- [ ] `docker compose up -d` starts api + postgres + redis cleanly
- [ ] `curl http://localhost:9100/healthz` returns 200
- [ ] `POST /odoo-enterprise/iot/connect-box {serial_number}` returns
      `{pairing_code, pairing_uuid}` and persists in DB
- [ ] Repeated polls with same serial return same code (idempotent)
- [ ] `POST /iot/finalize-pair {pairing_code, db_uuid, server_url}`
      flips the code's state to consumed, creates a box record
- [ ] Next poll on same serial returns `{url, token, db_uuid}`
- [ ] All endpoints have pytest coverage
- [ ] CI: ruff + py_compile + yaml lint + shellcheck + docs all green

**DB schema (Alembic 0001)**:
```sql
-- See ARCHITECTURE.md §"Database schema" for full DDL.
-- Migration creates: tenant, box, pairing_code, cert, audit
-- Indexes: box_serial_idx, box_tenant_idx, cert_box_idx,
--          audit_ts_idx, pairing_expires_idx
```

**Endpoints**:
| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET  | /healthz | none | liveness |
| GET  | /readyz  | none | DB + Redis ready |
| POST | /odoo-enterprise/iot/connect-box | none (pi serial as identity) | rendezvous + poll |
| POST | /iot/finalize-pair | (none for MVP, JWT later) | DB-side pairing completion |
| GET  | /admin/tenants | (none for MVP, JWT later) | list tenants |
| GET  | /admin/boxes   | (none for MVP, JWT later) | list boxes |

**Estimated effort**: 4 days (one focused work-day per: scaffold,
endpoints+services, tests, CI+docker polish).

### Phase 2: ACME cert issuance via lego + Cloudflare DNS-01 ⏳ blocked on CF token

**Repo**: filamind-iot-proxy
**PR title**: `feat: phase 2 — ACME cert issuance via lego + Cloudflare DNS-01`
**Branch**: `feat/phase-2-acme`
**CF token required**: **YES** — operator must provide before merge.

**New files**:
```
backend/api/services/cert_issuer.py        # subprocess wrapper around lego
backend/api/routes/cert.py                 # POST /odoo-enterprise/iot/x509
backend/api/services/subdomain.py          # 8-hex-id allocation + collision check
docker-compose.yml                         # +volume: ./data/acme:/etc/lego
.env.example                               # +CLOUDFLARE_DNS_API_TOKEN, +CERT_BASE_DOMAIN
docker/lego-image/Dockerfile               # tiny image: alpine + lego binary
backend/tests/test_cert_issuance.py        # mocks lego subprocess
```

**Acceptance criteria**:
- [ ] `POST /odoo-enterprise/iot/x509 {db_uuid, identifier}` returns
      a real LE wildcard cert PEM + private key + subject_cn
- [ ] Cert subject is `*.<8hex>.box.filamind.app` (8-hex unique per box)
- [ ] Cert stored in `cert` table, encrypted private key
- [ ] Audit log row created with event=`cert.issued`
- [ ] Failure path (invalid token, LE rate-limit, etc.) returns 502 with
      structured error body, NOT 500
- [ ] `data/acme/` volume persists LE account key across restarts
- [ ] CI green incl. new tests with subprocess mocking

**Encryption**:
Private keys at rest use Fernet (`cryptography` lib) with key derived
from `PROXY_MASTER_KEY` env var. Document key-rotation procedure.

**Estimated effort**: 3 days.

### Phase 3: Reverse tunnel via frp ⏳

**Repo**: filamind-iot-proxy
**PR title**: `feat: phase 3 — frp reverse tunnel for boxes behind NAT`
**Branch**: `feat/phase-3-frp`
**CF token required**: NO (use Phase 2's)

**New files**:
```
docker-compose.yml                         # +service: frps
frps/frps.toml                             # frps server config
frps/frps-Dockerfile                       # alpine + frps binary
backend/api/services/tunnel.py             # assign tunnel_subdomain on cert issue
backend/api/routes/tunnel.py               # POST /admin/boxes/<id>/regenerate-tunnel-token
caddy/Caddyfile                            # +block for *.tunnel.filamind.app → frps
```

**Acceptance criteria**:
- [ ] Phase 2 cert issuance also assigns a `tunnel_subdomain` like
      `box-1f29028f.tunnel.filamind.app`
- [ ] Box can run `frpc` against `iot-proxy.filamind.app:7000` with the
      assigned token + subdomain
- [ ] Browser hitting `https://box-1f29028f.tunnel.filamind.app` reaches
      the box's nginx via the reverse tunnel
- [ ] Disconnecting frpc from box → 502 to browser within 5s
- [ ] Heartbeat every 30s; missed > 5 → box marked offline in DB

**Estimated effort**: 3 days.

### Phase 4: Admin REST API + thin Odoo addon ⏳

Two sub-PRs, in this order. Phase 4b depends on Phase 4a.

#### Phase 4a: Admin REST API

**Repo**: filamind-iot-proxy
**PR title**: `feat: phase 4a — admin REST API + JWT auth`
**Branch**: `feat/phase-4a-admin-api`

**New files**:
```
backend/api/auth.py                        # JWT validate + issue
backend/api/routes/admin.py                # CRUD for tenants/boxes/certs
backend/api/services/admin_audit.py        # audit log writer
backend/tests/test_admin_api.py
```

**Endpoints (all under /admin/, all JWT-authed)**:
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /admin/auth/login | `{email, password}` | `{token}` |
| GET  | /admin/tenants | — | `[{id,name,plan,box_count,...}]` |
| POST | /admin/tenants | `{name,plan,box_quota}` | tenant |
| GET  | /admin/boxes | `?tenant_id=&status=` | paged list |
| POST | /admin/boxes/<id>/suspend | — | box |
| POST | /admin/boxes/<id>/decommission | — | box |
| POST | /admin/boxes/<id>/regenerate-cert | — | new cert |
| POST | /admin/boxes/bulk-update-proxy-url | `{from,to,box_ids?}` | task id |
| GET  | /admin/certs | `?expires_before=` | list |
| GET  | /admin/audit | `?since=&actor=` | paged list |

**Estimated effort**: 3 days.

#### Phase 4b: Thin admin addon

**Repo**: filamind-iot
**PR title**: `feat: filamind_iot_proxy_admin — Odoo addon (thin REST client)`
**Branch**: `feat/proxy-admin-addon`

**New addon**: `addons/filamind_iot_proxy_admin/`

**Files**:
```
__init__.py
__manifest__.py                            # depends ['filamind_iot']
models/__init__.py
models/proxy_settings.py                   # res.config.settings extension:
                                           #   proxy_url, proxy_token (encrypted)
models/proxy_tenant.py                     # filamind.proxy.tenant (REST-mirrored)
models/proxy_box.py                        # filamind.proxy.box
models/proxy_cert.py                       # filamind.proxy.cert
services/__init__.py
services/proxy_client.py                   # requests.Session wrapper, JWT refresh
views/proxy_settings_views.xml             # res.config.settings panel
views/proxy_tenant_views.xml
views/proxy_box_views.xml
views/proxy_cert_views.xml
views/proxy_menus.xml                      # under IoT > Proxy
data/cron_data.xml                         # sync_with_proxy every 5 min
security/ir.model.access.csv
README.md
```

**Acceptance criteria**:
- [ ] Admin enters proxy URL + token in Settings
- [ ] Cron syncs tenants/boxes/certs from proxy every 5 min
- [ ] Form view actions trigger REST calls (suspend, regenerate cert)
- [ ] All errors from proxy surface as Odoo notifications
- [ ] Works with `filamind_iot` umbrella; no duplicate `iot.box` records
- [ ] `filamind_iot_full` umbrella manifest updated to include this addon

**Estimated effort**: 4 days.

### Phase 5: filamind-iotbox patch 009 ⏳

**Repo**: filamind-iotbox
**PR title**: `feat: patch 009 — configurable proxy URL via homepage`
**Branch**: `feat/patch-009-configurable-proxy`
**Tracking**: filamind-iotbox#5

See [filamind-iotbox#5](https://github.com/filamind-app/filamind-iotbox/issues/5)
for the full design. TL;DR:

**Files**:
```
patches/009-configurable-proxy-url.patch  # touches system.py + connection_manager.py
                                           #         + certificate.py + homepage.py
src/iot_drivers/static/src/app/components/dialog/ServerDialog.js
                                           # + IoT Proxy URL field (optional)
scripts/build-image.sh                     # apply patch 009
scripts/flash-patches.sh                   # apply patch 009
scripts/verify-image.sh                    # assert patch 009 markers
```

**Acceptance criteria**:
- [ ] Empty proxy URL = upstream Odoo (byte-identical to today)
- [ ] Custom proxy URL written to `[iot.box] proxy_url`
- [ ] Switching URL clears stale token + db_uuid + enterprise_code
- [ ] HTTPS-only validation
- [ ] Sequential CI patch test passes

**Survival post-re-pair (separate sub-PR)**:
- Implement option C from the issue: vendor a runtime monkey-patch
  `filamind_proxy_url_loader.py` in `src/iot_drivers/drivers/` (already
  proven to survive `git clean -dfx`)

**Estimated effort**: 2 + 2 days.

### Phase 6: Monitoring + alerts ⏳

**Repo**: filamind-iot-proxy
**PR title**: `feat: phase 6 — Prometheus metrics + cert-expiry alerts`

**Files**:
```
docker-compose.yml                         # +prometheus +grafana
prometheus/prometheus.yml
grafana/dashboards/proxy.json
backend/api/routes/metrics.py              # /metrics endpoint (Prometheus format)
backend/api/services/notifier.py           # email + Slack webhook abstraction
backend/api/cron/health_check.py           # apscheduler — every 5min
                                           # alerts on: cert <30d to expiry,
                                           # box not seen 1h, ACME failure
```

**Estimated effort**: 2 days.

### Phase 7: Production hardening + deployment ⏳

**Repo**: filamind-iot-proxy
**PR title**: `feat: phase 7 — production deployment + backup + DR`

**Files**:
```
deploy/production/docker-compose.prod.yml
deploy/production/.env.template
deploy/production/backup.sh                # pg_dump → s3-compatible storage
deploy/production/restore.sh
deploy/production/cf-dns-records.tf        # Terraform for the 3 A records
docs/DEPLOYMENT.md
docs/RUNBOOK.md                            # incident playbooks
```

**Acceptance criteria**:
- [ ] `iot-proxy.filamind.app` resolves and serves a real LE cert
      (Caddy auto-ACME for the proxy itself)
- [ ] Three test boxes pair via proxy and get certs
- [ ] Reverse tunnel works for one box behind NAT (over Wi-Fi → Internet)
- [ ] Backup runs daily, restore tested
- [ ] Monitoring alerts fire on intentional failures

### Phase 8: License gate (optional, post-MVP)

**Repo**: filamind-iot-proxy
**PR title**: `feat: phase 8 — license gate for gated-mode tenants`

Only if operator decides to charge for proxy access. Adds:
- `tenant.license_key` JWT validation
- `/admin/licenses/issue` endpoint (operator generates keys)
- Stripe webhook integration (optional)
- Refusal of cert issuance for unlicensed/expired tenants

---

## 6. Side tracks (parallel work, lower urgency than the proxy)

Tracked as separate issues. Can be done by anyone in parallel.

### Side A: Field-gap fixes (filamind-iot)
**Tracking**: [filamind-iot#4](https://github.com/filamind-app/filamind-iot/issues/4)

Recommended order (one PR per group):
1. Critical naming aliases (5 fields) → unblocks Enterprise import
2. Missing fields per addon (11 fields)
3. New `pos.printer.iot_use_lna` field  
4. New addons `pos_event_iot` + `event_sale_iot`

Target release: `filamind-iot v1.2.0`.

### Side B: Customer Display 500 fix (filamind-iot)
**Tracking**: (not yet filed; waiting on this roadmap)

The `point_of_sale` Community-side polling loop hits
`http://localhost:8069/hw_proxy/...` from the cashier browser → fails.
Fix: OWL patch in `filamind_pos_iot` overrides the URL to use
`<iot_box.ip>:443/hw_proxy/...`.

Single PR. ~2 days.

### Side C: Box-side patch survival across re-pair
**Tracking**: [filamind-iotbox#5](https://github.com/filamind-app/filamind-iotbox/issues/5)
(option C in that issue)

Currently `git clean -dfx` wipes our patches when the user re-pairs.
Long-term fix: ship our changes as a runtime monkey-patch loaded from
`drivers/filamind_proxy_url_loader.py` (which survives `git clean`).

---

## 7. Operational state

### Live deployments

| What | Where | Owner | Notes |
|---|---|---|---|
| Customer Odoo (Enterprise + filamind addons) | https://deltafabs.com | customer | Currently running v1.1.0 of filamind-iot |
| Customer IoT Box | 192.168.0.254 (LAN) | customer | Re-paired with Odoo Enterprise (`payout.odoo.com`); has filamind drivers + helpers but git-tracked patches WIPED on re-pair |
| filamind-iot-proxy | (not deployed yet) | — | Will deploy at Phase 7 to `iot-proxy.filamind.app` |

### SSH access to servers

| Server | IP | User | Method | Notes |
|---|---|---|---|---|
| Customer Odoo | 157.90.152.154 | root | password (`Myserver@1209`) | Test creds, OK to use |
| Customer Box | 192.168.0.254 | pi | SSH key (already deployed in WSL `~/.ssh/id_ed25519`) | Or password rotated via `/iot_drivers/generate_password` |
| Customer Enterprise SaaS | https://payout.odoo.com | eg2@live.co.uk | password (`Myserver@1200`) | Odoo Enterprise admin |

### DNS state
All operator domains hosted at Cloudflare. To-be-added records (Phase 7):
```
iot-proxy.filamind.app   A      <proxy-server-public-ip>
*.box.filamind.app       A      <proxy-server-public-ip>
*.tunnel.filamind.app    A      <proxy-server-public-ip>
```

### Locations on operator's customer server (`/home/deltafabs.com/...`)
- Filamind addons: `custom_addons/filamind_*` (14 addons, **NOT** `filamind/` which is unrelated 3D-printer product)
- Pre-upgrade backup: `filamind-upgrade-backups/v1.1.0-20260511-110837/`
- Odoo container: `odoo-web` (in Docker)
- Postgres: `odoo-db` container, password `Myserver@1200`

---

## 8. Conventions (binding for all 3 repos)

- **Python**: 3.12, ruff for lint, py_compile in CI
- **Node**: 20, `node --check` for any JS files
- **Shell**: bash, `bash -n` + shellcheck `-e SC1091,SC2086,SC2155`
- **Commits**: imperative mood (`fix: X`, `feat: Y`, `docs: Z`)
- **Co-author tag**: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
- **Branches**: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `ci/<topic>`
- **PRs**: 1 PR = 1 cohesive change. Title summary + body with Summary + Test plan
- **Branch protection on main**: required CI green, no force push, no deletion, conversation resolution required
- **Tags**: per-addon (`<addon>/v0.X.Y`) for filamind-iot; `v0.X.Y` for filamind-iotbox + proxy
- **Releases**: created automatically by tag-pushed workflow
- **Docs**: keep README + CHANGELOG + per-PR description in sync; major architectural decisions go in this ROADMAP

---

## 9. Migration paths (must always remain true)

### Domain change (e.g. filamind.app → other.com)
**Pre-requisite**: patch 009 deployed on every active box.

1. Add new DNS records, keep old
2. Caddy config supports both old + new vhosts
3. Issue certs for new wildcard zone
4. Either (slow): wait one cert cycle (~60d) — boxes auto-migrate at next renewal
5. Or (fast): admin pushes `bulk-update-proxy-url` command via REST API → all boxes pick up new URL on next heartbeat (~5 min)
6. Decommission old DNS + Caddy block after all boxes migrated

### Server change (e.g. existing → dedicated VPS)
**Cold approach (~15 min downtime)**:
1. Stop services on old: `docker compose down`
2. `pg_dump` + `tar /data/acme /data/frps` → new server
3. `docker compose up` on new with same env
4. Update Cloudflare DNS A → new IP
5. Wait propagation (~5 min); boxes auto-reconnect

**Hot approach (~0 downtime)**:
- Set DNS TTL to 60s 24h before
- Set up Postgres logical replication old → new
- Switch DNS atomically once new caught up

---

## 10. What NOT to do (lessons from prior session)

1. **Never push directly to `main` on any of the 3 repos.** Branch
   protection enforces this; PR-only workflow.

2. **Never use `filamind*` glob without underscore on the customer
   server.** `filamind_*` (with underscore) is required so the
   unrelated 3D-printer `filamind/` directory is never touched. See
   [memory file project_filamind_two_products.md](https://...)

3. **Don't tag a release before the matching CI pipeline goes fully
   green.** v1.0.0 of filamind-iot was tagged before Odoo Integration
   CI existed; 8 critical bugs slipped through. v1.1.0 is the first
   tag created post-CI-validation.

4. **Don't modify upstream Odoo files via patches when re-pair will
   `git clean -dfx`.** Use vendor drivers in `iot_drivers/drivers/`
   (which survive) or runtime monkey-patches.

5. **Don't deploy without backup.** `tools/upgrade.sh` + the proxy's
   own `backup.sh` make backups mandatory before every upgrade.

6. **Don't add features beyond the task at hand.** Bug fixes don't
   need surrounding refactors; one-shot operations don't need
   helpers; three similar lines is better than a premature abstraction.

---

## 11. Acceptance criteria for v1.0 of the proxy

A successful **v1.0.0 of `filamind-iot-proxy`** requires:

- [ ] All Phases 1-7 merged
- [ ] Deployed to `iot-proxy.filamind.app`
- [ ] One real customer box (the deltafabs box at `192.168.0.254`)
      paired via the proxy instead of Odoo's
- [ ] Customer's POS workflow works end-to-end through the proxy:
      print receipt, weigh on scale, customer display
- [ ] Cert auto-renewal verified by manually expiring + observing reissue
- [ ] Reverse tunnel verified: external browser hits
      `https://<box-id>.tunnel.filamind.app` and reaches box nginx
- [ ] Backup + restore tested end-to-end
- [ ] Monitoring alerts proven by intentionally failing a check
- [ ] Documentation: DEPLOYMENT.md + RUNBOOK.md complete

---

## 12. Estimated total effort

| Phase | Effort | Cumulative |
|---|---|---|
| Phase 1: Pairing API | 4d | 4d |
| Phase 2: ACME | 3d | 7d |
| Phase 3: Reverse tunnel | 3d | 10d |
| Phase 4a: Admin API | 3d | 13d |
| Phase 4b: Odoo addon | 4d | 17d |
| Phase 5: Patch 009 | 2+2d | 21d |
| Phase 6: Monitoring | 2d | 23d |
| Phase 7: Deployment | 2d | 25d |
| **MVP / v1.0.0** | | **25 working days** |
| Phase 8: License gate | 3d | optional |
| Side A: Field gaps | 5d | parallel |
| Side B: Customer Display fix | 2d | parallel |
| Side C: Patch survival | 2d | parallel |

---

## 13. Where this roadmap lives

- Canonical: `filamind-iot-proxy/ROADMAP.md` (this file)
- Cross-referenced from:
  - `filamind-iot-proxy/README.md`
  - `filamind-iot-proxy/REQUIREMENTS.md`
  - `filamind-iot-proxy/ARCHITECTURE.md`
  - GitHub issues `filamind-iot#4`, `filamind-iotbox#5`

When this roadmap changes, update the "Last updated" line at the top
and open a PR with the diff. Do NOT update via direct commit to main
(branch protection will reject it anyway).
