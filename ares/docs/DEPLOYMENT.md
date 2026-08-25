# Deploying ARES as a web app

The goal: open a URL on your phone or laptop and ARES loads. No dev tools, no
manually starting two processes.

ARES ships as **one process**. The FastAPI backend serves the API, the
WebSocket and the built web app from the same origin, so there is a single port
and a single URL for every device.

## Option A — Docker (recommended)

```bash
cd ares
cp .env.example .env         # fill in; never commit
docker compose up -d --build
```

Open `http://<host>:8000`. Verify with `curl http://<host>:8000/api/health`.

The compose file persists the trade journal in a named volume, restarts the
container automatically, and health-checks the process.

## Option B — no Docker

```bash
cd ares
cp .env.example .env
./scripts/serve.sh           # builds the web app if needed, then serves
```

To run it permanently on Linux, use the sample unit in
`scripts/ares.service`.

## Reaching it from your phone

**Same network:** the server binds `0.0.0.0`, so
`http://<laptop-LAN-IP>:8000` works from any device on the same Wi-Fi.

**From anywhere:** put a TLS terminator in front. Any of these work:

* **Cloudflare Tunnel** — no open ports, gives you an HTTPS hostname:
  `cloudflared tunnel --url http://localhost:8000`
* **Caddy** — automatic certificates:
  ```
  ares.example.com {
      reverse_proxy localhost:8000
  }
  ```
* **nginx** — remember the WebSocket upgrade headers for `/ws` and `/bridge/ws`.

HTTPS is required in practice, not optional: the PWA service worker only
registers on a secure origin, and the access token travels in a header (and in
the WebSocket query string), so it must be encrypted in transit.

## Securing the deployment

Before ARES is reachable from the internet, set an access token:

```
ARES_ACCESS_TOKEN=<long random string>
```

Every `/api/*` route and the client WebSocket then require it. `GET
/api/health` stays public for uptime checks. The browser prompts once and
stores the token locally — it is **never** compiled into the JavaScript bundle.
Settings → Security shows whether the deployment is actually enforcing a token
or is currently open.

Generate secrets with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Environment variables

All secrets come from the environment. Nothing sensitive is ever hard-coded or
exposed to the frontend.

| Variable | Purpose |
|---|---|
| `ARES_ACCESS_TOKEN` | gate the web app and API |
| `ARES_BRIDGE_TOKEN` | authenticate the Windows MT5 bridge |
| `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` / `MT5_PATH` | set on the **bridge machine**, not the server |
| `ARES_AI__PROVIDER` / `ARES_AI__API_KEY` | optional narration provider |
| `ARES_MARKET_DATA__MODE` | `mt5` (default) or `simulation` |
| `ARES_NEWS__NEWS_FEED_ENABLED` | turn the RSS news engine on/off |
| `ARES_SYSTEM__DATABASE_URL` | SQLite by default; PostgreSQL-ready |
| `ARES_RISK__*` | risk limits (also editable in Settings) |

## Installing as a PWA

Once ARES is served over HTTPS:

* **iPhone / iPad (Safari):** open the URL → Share → **Add to Home Screen**.
  ARES launches standalone, without browser chrome, and respects the notch.
* **Android (Chrome):** open the URL → menu → **Install app** (or the install
  prompt in the address bar).
* **Desktop (Chrome/Edge):** the install icon at the right of the address bar.

The service worker caches only the app shell — HTML, JS, CSS and icons — so
launches are instant. It **never** caches `/api/*`: prices, positions, account
state and news always come from the network, because a cached price is a wrong
price. Offline, ARES loads and tells you data is unavailable rather than
showing stale numbers.

## Health and monitoring

* `GET /api/health` — process liveness plus every component's real state.
* `GET /api/status` — the same, with session information (token-protected).
* `GET /api/bridge` — MT5 bridge state, for alerting on a dropped bridge.

Logs are single-line JSON with passwords and API keys redacted at the handler,
so they are safe to ship to a log collector.

## Upgrading

```bash
git pull
docker compose up -d --build     # or: ./scripts/serve.sh after npm run build
```

The service worker is network-first for navigations, so a new deploy is picked
up on the next load rather than being pinned by the cache.
