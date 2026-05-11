# Reverse tunnel (Phase 3)

This document covers the optional reverse-tunnel hub bundled with
`filamind-iot-proxy`. It lets a box behind a home/office NAT be
reachable at `https://<short-box-id>.tunnel.<your-zone>` without
opening any inbound ports on the customer's network.

The hub is **opt-in**: nothing in Phase 1, 2, 4, or 5 depends on it.
Customers without remote-support needs can ignore everything below.

---

## Architecture

```
[Box on customer LAN]                  [filamind-iot-proxy host]
    nginx :443  ◄────┐                     frps :7000  (control)
                     │                     frps :7443  (vhost-https)
                  frpc ───── outbound TCP ─►
                  ▲
                  └── installed via patch 011 (TBD, Phase 5 follow-up)
```

The box's local nginx serves the IoT homepage on `:443` with a
self-signed cert. `frpc` (frp client) opens an outbound TCP
connection to the hub on port 7000 and registers
`<short-box-id>` as its subdomain. The hub then accepts public
HTTPS traffic for `<short-box-id>.tunnel.<your-zone>` and
forwards it back over the existing control channel to the box.

No inbound port is opened on the customer's router.

---

## Server-side (this repo)

1. Edit `.env` with a long random `FRP_TOKEN`, a `FRP_DASHBOARD_PASSWORD`,
   and (optionally) override ports. Then:

   ```bash
   docker compose --profile tunnel up -d proxy-frps
   ```

2. Verify:

   ```bash
   docker compose logs proxy-frps | tail -20
   # Should show "frps started"
   curl -sf http://localhost:7500 -u admin:$FRP_DASHBOARD_PASSWORD \
       | head -20
   ```

3. Public DNS: add `*.tunnel.<your-zone> A <proxy-host-public-ip>` at
   your DNS provider (Cloudflare orange-cloud is fine — vhost-HTTPS
   passes through). The control port (`7000`) is opened in your
   firewall too.

---

## Box-side (frpc) — manual smoke test

> The fully-automated box install lands in a follow-up Phase 5 patch
> (012 — frpc systemd unit + token write-back). The snippet below is
> for ops-side smoke testing only.

On the Pi:

```bash
sudo apt-get install frpc
sudo tee /etc/frp/frpc.toml >/dev/null <<EOF
serverAddr = "iot-proxy.filamind.app"
serverPort = 7000
auth.method = "token"
auth.token  = "<the same FRP_TOKEN from the server .env>"

[[proxies]]
name = "homepage-$(cat /etc/filamind/short-box-id)"
type = "https"
localIP   = "127.0.0.1"
localPort = 443
customDomains = []
subdomain = "$(cat /etc/filamind/short-box-id)"
EOF
sudo systemctl enable --now frpc
```

The box's homepage is then reachable at
`https://<short-box-id>.tunnel.<your-zone>`. The cert chain on that
endpoint is whatever Caddy serves (Phase 7) — usually a wildcard
Let's Encrypt for `*.tunnel.<your-zone>`.

---

## Security notes

- `FRP_TOKEN` is the **only** thing standing between the public
  internet and unrestricted vhost registration. Rotate it whenever
  a box is decommissioned. Treat it like an admin token.
- The frps dashboard (`:7500`) is bound to `127.0.0.1` on purpose.
  Reach it over `ssh -L 7500:127.0.0.1:7500 <proxy-host>`.
- vhost-HTTPS (`:7443`) is also `127.0.0.1` until Caddy fronts it on
  the public 443. Don't expose 7443 directly to the internet without
  a TLS-terminating reverse proxy.
- Each frpc carries the shared token. If one box is compromised,
  rotate the token everywhere (server + every box). The Phase 4
  admin API will gain a per-box subdomain revocation in a future
  release.

---

## Limits / known issues

- frps does not currently store quotas/usage in the proxy's
  Postgres. The Phase 3 hub is "fire-and-forget"; the dashboard
  is the source of truth for active tunnels.
- The subdomain naming uses the **short box id** (first 8 chars of
  the box UUID). For >65k boxes per zone, switch to the full UUID.
- A single token covers all boxes. Per-box tokens require a fork
  of frps or an upstream feature request.
