# ARES Roadmap & Phase Status

Build environment: Linux host, Python 3.11.15, Node 22, npm 10.9.7.

## Original build (phases 1–16)

| Phase | Scope | Status |
|---|---|---|
| 1 | Foundation — structure, config, .env protection, logging, status registry, health, MT5 detection | **COMPLETE** |
| 2 | UI shell | **SUPERSEDED** by the executive redesign (phase 17) |
| 3 | Market data — providers, tick loop, caching, WebSocket | **COMPLETE** |
| 4 | Charts — candlesticks, 8 timeframes, volume, live updates, overlays | **COMPLETE** |
| 5 | Technical analysis — trend, swings, S/R, liquidity, BOS/CHOCH, premium/discount | **COMPLETE** |
| 6 | AI Command Center — intents, structured analysis, app control | **COMPLETE** |
| 7 | MT5 integration | **COMPLETE** via the Windows bridge (phase 18) |
| 8 | Demo/paper trading | **COMPLETE** |
| 9 | Risk management | **COMPLETE** |
| 10 | Market scanner | **COMPLETE** (now inside the Analysis workspace) |
| 11 | News / web intelligence | **COMPLETE** — real RSS engine (phase 19) |
| 12 | Journal + analytics + coaching | **COMPLETE** |
| 13 | Takeover Mode | **COMPLETE** |
| 14 | Performance | **COMPLETE** |
| 15 | Security + testing | **COMPLETE** |
| 16 | Final polish | **COMPLETE** |

## Overhaul (phases 17–22)

| Phase | Scope | Status | Notes |
|---|---|---|---|
| 17 | Executive design system + full UI rebuild | **COMPLETE** | New tokens, nav, Command Center workspace, Risk Command, Analysis, Settings; verified at 1600/834/390 px |
| 18 | Windows MT5 bridge | **COMPLETE** | Protocol, server, adapter, Windows client, precise states; data path verified end-to-end in an automated test |
| 19 | Real news engine | **COMPLETE (code)** / **DATA BLOCKED HERE** | RSS/Atom ingestion, classification, impact, interpretation. This sandbox's network policy blocks all news hosts, so the feed is correctly empty here; it populates on any host with normal egress |
| 20 | Responsive + PWA | **COMPLETE** | Per-device layouts, manifest, icons, shell-only service worker |
| 21 | Production packaging | **COMPLETE** | Single-process serving, Dockerfile, compose, serve.sh, systemd unit, access token |
| 22 | Deployment to a public URL | **NOT DONE** | Cannot be done from this environment — see below |

## Deployment status (explicit)

**There is no production URL.** ARES is packaged and verified to run as a
single-process web app, but this build environment is an ephemeral sandbox with
no public ingress and no hosting credentials, so nothing was actually deployed.
Claiming otherwise would be false.

What *was* verified here: the backend serves the SPA, manifest, service worker
and deep links on one port; the access token gate rejects unauthenticated API
and WebSocket clients; the bridge protocol carries real market data end-to-end;
and the UI renders correctly on desktop, tablet and phone viewports.

To get a URL, run one of the documented paths in `docs/DEPLOYMENT.md` (Docker
Compose behind Caddy or a Cloudflare Tunnel is the shortest route).

## Known limitations

- **No public deployment** (above). One command on your own host or VPS.
- **MT5 requires the Windows bridge.** Verified against a protocol-level test
  client, not yet against a live broker terminal — that needs your Windows
  machine and demo credentials.
- **News needs network egress** to the source hosts; blocked in this sandbox.
- **Economic calendar has no live feed.** Events are added manually or by a
  future licensed integration; ARES never invents them.
- **Web research layer** is absent — reported as unavailable rather than faked.
- **Paper P/L** converts quote-currency P/L 1:1 to the account currency (JPY
  pairs adjusted). Fine for demo metrics, not broker-exact.
- **No live-money execution path** exists in this build, by design.

## Next steps

1. Deploy with Docker Compose behind TLS; install the PWA on your phone.
2. Stand up the Windows bridge against your demo account and run the four
   verification checks in `docs/MT5_BRIDGE.md`.
3. Confirm the news feed populates once ARES runs on a host with normal egress.
4. Optional: licensed calendar/news feed, PostgreSQL profile, multi-user auth.
