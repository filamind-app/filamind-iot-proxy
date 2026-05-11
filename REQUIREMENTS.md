# Requirements before implementation can start

> See also: [ROADMAP.md](ROADMAP.md) for which phase each requirement
> blocks. Phase 1 (Pairing API + DB schema) needs none of these and
> can ship now. Phase 2 (ACME) blocks on the Cloudflare API token.

This document lists every input the operator (you) needs to provide
before `filamind-iot-proxy` can be built and deployed. Items marked
**REQUIRED** must be answered before any code is written; items marked
**OPTIONAL** can be deferred until later phases.

---

## 1. Brand / domain — **REQUIRED**

The proxy needs a base domain to serve from and a wildcard subdomain
to mint per-box certs under.

| Field | Example | Your value |
|---|---|---|
| Proxy public hostname | `iot-proxy.your-brand.com` | _to be decided_ |
| Wildcard cert zone | `*.box.your-brand.com` | _to be decided_ |
| Brand name in UI | "MyCorp IoT" | _to be decided_ |
| Brand logo (PNG, ≥256px) | (file) | _to be provided later_ |

**Constraints:**
- The wildcard zone (`*.box.<x>`) must be a DNS zone you own and can
  add `TXT` records to via API (DNS-01 ACME challenge).
- The proxy hostname needs a public A record pointing at the host that
  will run the Docker stack.
- Both can be on the same registered domain (e.g.
  `iot-proxy.example.com` + `*.box.example.com` — both under
  `example.com`).

**Suggestions if you want to defer this:**
- Use a placeholder domain in dev (e.g. `iot-proxy.local` with a
  self-signed cert + `/etc/hosts` entries).
- Production-ready domain can be plugged in later via `.env` rebuild.

---

## 2. DNS provider — **REQUIRED**

For ACME DNS-01 we need API access to the DNS provider hosting the
wildcard zone.

| Field | Notes | Your value |
|---|---|---|
| DNS provider | Cloudflare / Route53 / DigitalOcean / ... | _to be decided_ |
| API token | scoped to the zone, `Zone.DNS:Edit` only | _to be provided_ |
| Zone ID (Cloudflare) or zone name | `box.your-brand.com.` | _to be provided_ |

**Minimum scopes (Cloudflare example):**
- `Zone.DNS` permission, `Edit`
- Restricted to the specific zone (`box.your-brand.com`)
- **NOT** account-level — least privilege

**Why this matters:** the proxy will create + delete `TXT` records
during cert issuance. With anything more powerful, a compromise blasts
your whole zone.

---

## 3. Static DNS records (one-time, you create) — **REQUIRED**

After domain is decided, three records to add at your DNS provider:

```
iot-proxy.your-brand.com   A       <proxy-server-public-ip>
*.box.your-brand.com       A       <proxy-server-public-ip>
*.tunnel.your-brand.com    A       <proxy-server-public-ip>     # optional, for §6
```

If you front it with Cloudflare proxying, the box `A` records can be
proxied (orange cloud) — the cert ACME still works because we use
DNS-01 (no port-80 challenge).

---

## 4. Hosting target — **REQUIRED**

Where will the proxy stack run?

| Option | Pros | Cons |
|---|---|---|
| **Existing customer server** (`157.90.152.154`) | Free, fast to deploy | Shares resources with Odoo + NetBird + Authentik |
| **Dedicated tiny VPS** (Hetzner CX22 €4.51/mo) | Isolated, scales to thousands of boxes | Extra cost + ops overhead |
| **Kubernetes cluster** (later) | HA, multi-region | Premature for MVP |

**Recommendation:** ship MVP on existing server, migrate to dedicated
VPS once it has > 50 active boxes.

| Field | Your choice |
|---|---|
| Hosting target | _to be decided_ |
| Memory budget | _suggested: 1 GB for MVP, 4 GB at scale_ |
| Disk budget | _suggested: 10 GB (mostly Postgres + ACME state)_ |

---

## 5. License / subscription model — **REQUIRED (binary choice)**

| Mode | Behaviour |
|---|---|
| **Open** | Anyone can pair + get a cert. No license check. (filamind ethos.) |
| **Gated** | Pairing + cert issuance refused unless tenant has a valid `license_key`. License keys are issued out-of-band (you sell them). |

Either is implementable. Open is faster to MVP. Gated requires:
- A separate license-issuance flow (Stripe / manual / whatever)
- A `licenses` table in the proxy DB
- License-validation middleware in every gate-able endpoint

| Field | Your choice |
|---|---|
| License model | _to be decided_ |

---

## 6. Reverse tunnel (`frp`) — **OPTIONAL**

If your customers' boxes are behind home/office routers with no public
IP, the proxy can act as a TCP/HTTPS reverse-tunnel hub so the box is
reachable at `https://<box-id>.tunnel.your-brand.com`.

This enables:
- POS browsers on the same LAN as the box (works without VPN)
- Customer Display flows (no mixed-content errors)
- Remote support: `ssh -p <port> pi@<box-id>.tunnel.your-brand.com`

**Costs:**
- One extra public TCP port (default 7000)
- ~10 MB RAM per active tunnel
- Bandwidth (passes through proxy server)

| Field | Your choice |
|---|---|
| Enable reverse tunnel | _yes / no / "later"_ |

If "later": the rest of the proxy ships without it; can be added with
no breaking changes to box-side code.

---

## 7. Operator notifications — **OPTIONAL**

For cert-expiry alerts, pairing failures, and box-down events:

| Channel | Inputs needed |
|---|---|
| Email (SMTP) | host, port, user, pass, from-address, to-address |
| Slack / Discord | webhook URL |
| PagerDuty | integration key |
| (none) | logs only |

**Suggested for MVP**: email to a single ops mailbox.

---

## 8. Backup / DR — **REQUIRED at deploy time, not now**

Postgres dump every N hours, ACME account key separately backed up.
Decided at deploy time; nothing needed during implementation.

---

## 9. Observability — **OPTIONAL**

Prometheus + Grafana (already in Docker compose) or external
monitoring service:

| Field | Your choice |
|---|---|
| Metrics endpoint | bundled Prom / Datadog / external Prom / none |

---

## 10. Source-code visibility — **REQUIRED**

| Mode | Notes |
|---|---|
| **Public LGPL-3** (recommended, matches filamind-iot) | Customers can audit + self-host |
| Private repo | Restricts contribution, requires personal-license model |

| Field | Your choice |
|---|---|
| Public / private | _LGPL-3 public assumed unless you say otherwise_ |

---

## Summary of inputs to send back

Bare minimum to start writing code:

```
Domain:           iot-proxy.<X>.com  +  *.box.<X>.com
DNS API:          provider + scoped token
Hosting:          existing server / new VPS
License model:    open / gated
Reverse tunnel:   yes / no / later
Brand UI name:    "<X>"
```

Everything else can be plugged in incrementally.
