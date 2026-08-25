# ARES Architecture

## Principles

1. **No fake intelligence.** Every component reports a verified state
   (ONLINE / DEGRADED / OFFLINE) with the real reason. Prices, accounts,
   news, and execution results are never fabricated. The simulation feed is
   opt-in and labeled `SIMULATED` end-to-end.
2. **Deterministic evidence, optional narration.** Bias, structure, levels,
   and the 1–5 confidence score come from measurable code
   (`analysis/confidence.py`), never from an LLM. A configured LLM only
   narrates the structured result.
3. **Execution is guarded in depth.** Paper-only build → risk engine on
   every order → Takeover requires explicit out-of-band authorization with
   hard caps → emergency stop closes everything and blocks execution.
4. **Fail gracefully.** Any subsystem can be offline while the rest runs.

## Deployment shape

ARES runs as **one process**. FastAPI serves the API, the client WebSocket, the
bridge WebSocket, and the built SPA from a single origin — so there is one URL
for phone, laptop and desktop, no CORS in production, and no separate frontend
server to start.

```
                 ┌─────────────────────────────────────────┐
  phone ────────▶│  ARES process (Linux / cloud / laptop)  │
  laptop ───────▶│                                         │
  desktop ──────▶│  /            SPA (built React bundle)  │
                 │  /api/*       REST                      │
                 │  /ws          live ticks, alerts        │
                 │  /bridge/ws   Windows MT5 bridge  ◀─────┼──── Windows + MT5
                 │  SQLite       journal                   │
                 └─────────────────────────────────────────┘
```

Access control is a single middleware: with `ARES_ACCESS_TOKEN` set, every
`/api/*` path and the client WebSocket require the token (header, bearer, or
query parameter for the socket). `/api/health` stays public for uptime probes.
Static assets stay public so the unlock screen can load. The token is supplied
by the user at runtime and stored in their browser — it is never compiled into
the bundle.

## MT5 access: two shapes, one interface

| Host | Path | Adapter |
|---|---|---|
| Windows with the terminal installed | direct terminal IPC | `MT5Adapter` + `MT5ConnectionMonitor` |
| Linux / cloud / macOS | Windows bridge dials in | `BridgeMT5Adapter` over `MT5BridgeServer` |

Both expose the same surface (`connected`, `get_tick`, `get_candles`,
`get_symbols`, `status_payload`), so the market-data service, analysis engine
and execution engine are unchanged by which one is active. `build_services()`
picks the direct adapter only when detection proves the package and terminal
are genuinely usable and credentials exist; otherwise it selects the bridge.

The bridge protocol is a small JSON RPC over one WebSocket:

* `hello` / `hello_ack` — token check, protocol version, terminal state.
* `heartbeat` (bridge → ARES, every ~15s) — carries the terminal's own state
  and non-sensitive account facts. No heartbeat for 45s ⇒ treated as gone.
* `request` / `response` — correlated by id, with per-call timeouts. A pending
  call raises when the bridge disappears, so callers degrade instead of hanging.

`ui_state` maps the bridge's report onto exactly what the interface shows:
`DISCONNECTED`, `CONNECTING`, `CONNECTED`, `ERROR`,
`MT5 TERMINAL NOT RUNNING`, `BROKER DISCONNECTED`, `AUTHENTICATION REQUIRED`,
`DISABLED`. There is no code path that reports CONNECTED without a live
heartbeat whose `terminal_connected` is true.

## News pipeline

```
DEFAULT_SOURCES ─▶ httpx (concurrent) ─▶ parse_feed (RSS 2.0 + Atom, stdlib)
        │                                        │
        │                                        ▼
        │                            classify(): symbols, currencies,
        │                            categories, impact, direction
        │                                        │
        ▼                                        ▼
  SourceStatus per feed              build_interpretation(): ARES's read,
  (ok / error / counts)              labelled and kept separate
                                                 │
                                                 ▼
                                    dedupe by URL hash, 3-day window,
                                    newest first, capped
```

Source text is reproduced verbatim (markup stripped, length-trimmed).
Everything ARES adds lives in `impact`, `ares_impact`, `ares_interpretation`
and `direction`. When no source is reachable, the article list is empty and the
status carries the real per-source errors — the UI then shows
"News unavailable" with the reason instead of anything invented.

## Backend (FastAPI, Python)

```
ARES START → load config → validate env → detect MT5 → connect (verified)
→ database → market-data service → analysis engine → AI verify
→ WebSocket hub → engine tick loop → ARES READY
```

### Key modules

| Module | Responsibility |
|---|---|
| `config.py` | `AresConfig` (pydantic-settings): AI / MT5 / MARKET_DATA / RISK / EXECUTION / TAKEOVER / NEWS / SYSTEM sections; `.env` + env vars; MT5_* conventional names |
| `status.py` | Central status registry; components start OFFLINE and are promoted only after verified checks |
| `mt5/detect.py` | Three-tier detection: platform support (Windows-only package), package availability, terminal path (configured + common installs) |
| `mt5/adapter.py` | One managed connection; CONNECTED only after account info **and** a live tick were retrieved; lazy import; thread-safe sync calls via executor |
| `mt5/monitor.py` | Liveness probe loop, safe bounded reconnection, execution-disable hooks on loss |
| `market_data/providers.py` | `MarketDataProvider` interface → `MT5Provider`, `SimulatedProvider` (seeded, deterministic, labeled) |
| `market_data/service.py` | Tick loop + WS broadcast, TTL candle cache per timeframe, symbol cache, change stats from D1 closes |
| `analysis/structure.py` | Fractal swings, trend (swing sequence + EMA + momentum), BOS/CHOCH, liquidity pools/sweeps, dealing range with premium/discount/equilibrium, S/R, volatility state |
| `analysis/engine.py` | H4/H1/M15 multi-timeframe analysis → structured schema (bias, confidence + factors, alignment, key levels, scenarios, invalidations, risks) |
| `analysis/confidence.py` | Evidence-based 1–5 scoring; each factor carries points + reason |
| `risk/engine.py` | Hard blocks: daily loss, drawdown %, open positions, exposure, session trades, position size, spread, post-loss cooldown, emergency stop |
| `execution/paper.py` | Validate → fill at real bid/ask → mark-to-market → SL/TP fills → history + account metrics (win rate, avg R, profit factor, drawdown) |
| `execution/baskets.py` | Basket grouping, combined P/L & exposure, max-loss enforcement, "Close Basket #ARES-104" |
| `execution/takeover.py` | State machine IDLE→REQUESTED→ACTIVE→COMPLETED/STOPPED/EXPIRED; authorization TTL; caps on trades/risk/duration; duplicate-order protection; auto-shutdown |
| `ai/provider.py` | `AIProvider` abstraction: Gemini / OpenAI / Anthropic; startup verification; key redaction |
| `ai/command.py` | Command Center: deterministic intent parsing + orchestration; UI actions; execution intents can only *request*, never authorize |
| `ai/coach.py` | Behavior-based coaching from the recorded journal (min-trades gate) |
| `mt5/bridge.py` | Bridge server: token handshake, heartbeat-driven state, correlated RPC, `BridgeMT5Adapter` |
| `security.py` | Optional access token for API + WebSocket; secrets redacted from logs |
| `news/feeds.py` | RSS 2.0 + Atom parsing (stdlib), source registry, category constants |
| `news/service.py` | Concurrent fetch, classification, impact scoring, ARES interpretation, truthful per-source status |
| `news/calendar.py` | Economic events (user/licensed-feed only — never fabricated); high-impact proximity warnings |
| `news/alerts.py` | Price alerts, risk/connection/execution events, WS broadcast |
| `scanner/scanner.py` | Concurrent evidence-ranked scan of watched symbols |
| `database.py` | Async SQLAlchemy + SQLite; journal persistence; PostgreSQL swap = URL change |
| `api/routes.py`, `api/ws.py` | REST surface + single WebSocket hub (`ticks`, `alert`, `account` messages) |

### API surface (excerpt)

```
GET  /api/health /api/status /api/account /api/symbols
GET  /api/market/{symbol} /api/candles/{symbol}?timeframe=&count=
POST /api/analyze /api/command
GET  /api/scanner /api/positions /api/trades /api/journal /api/coach /api/analytics
POST /api/order/validate /api/order/demo /api/position/close /api/basket/{id}/close
GET/POST /api/risk /api/risk/limits /api/risk/emergency-stop[/release]
GET/POST /api/takeover /api/takeover/request /api/takeover/authorize /api/takeover/stop
GET/POST /api/calendar /api/calendar/events /api/alerts /api/alerts/price
WS   /ws
```

## Design system

The interface is built on a small set of tokens rather than component library
defaults: layered warm near-black surfaces (`--s0`…`--s3`), hairline borders at
low alpha, a warm neutral type ramp, and **one** accent (brass) reserved for
active state, focus and key figures. Semantic colour is desaturated so a screen
full of numbers stays calm. A serif display face carries identity and headline
figures; small-caps labels organise the layout; tables use hairline rows with
no striping. Motion is limited to a 180 ms rise on new content, a slow breathe
on pending states, and a single settle pulse on changed values — all disabled
under `prefers-reduced-motion`.

Layouts are written per device rather than scaled: from `xl` the command
surface fills the viewport exactly and only inner regions scroll; on phones the
page scrolls, tables become thumb-sized rows, and navigation is a bottom bar of
the six priority areas with the rest behind a sheet.

## PWA

`manifest.webmanifest` (standalone display, maskable icons, brass-on-black
theme) plus a shell-only service worker. The worker caches HTML, hashed assets
and icons; navigations are network-first so a deploy is picked up immediately.
It **never** caches `/api/*`, `/ws` or `/bridge/*` — a cached price is a wrong
price, and serving one would be indistinguishable from fabricating it. Offline,
ARES loads and reports data as unavailable.

## Frontend (React + TS + Vite + Tailwind)

- **State**: one zustand store; theme/symbol/timeframe/favorites persisted in
  `localStorage`; sections stay mounted after first visit so chart state,
  filters and scroll survive navigation.
- **Live data**: exactly one managed WebSocket with exponential-backoff
  reconnect; ticks/alerts/account pushed, low-frequency polling only where a
  push channel doesn't exist yet.
- **Chart**: lightweight-charts v5 created once per section; candles fetched
  per symbol/timeframe with backend TTL caching; last candle updated from the
  tick stream; key levels, entries, SL/TP and markers drawn as overlays;
  re-themed without re-creation.
- **Sections**: Command Center (chart + briefing + chat + command bar),
  Markets, Chart (+ paper order ticket), Scanner, Positions (+ baskets, risk
  controls, takeover), Journal (+ coach), Analytics, News (calendar), Settings
  (MT5 diagnostics, risk limits, theme, notifications).
- **Responsive**: desktop rail navigation; intentional mobile layout with a
  bottom bar prioritizing Command/Chart/Markets/Positions.

## Data-source honesty model

| State | Meaning |
|---|---|
| `MT5 TERMINAL FOUND` | executable located; nothing verified |
| `MT5 CONNECTED` | initialize + login + account info + a real tick all succeeded |
| `MARKET DATA STREAMING` | market_data component ONLINE with `source: MT5` |
| `SIMULATED` | explicit demo feed; labeled on every tick, candle, analysis, scan row and in AI text |
| `DATA SOURCE OFFLINE` | neither of the above; endpoints return 503, orders are refused |

## Future work

- Live execution (architecturally isolated behind `ExecutionSettings`;
  requires verified demo/live gates and a Windows MT5 host).
- Licensed economic-calendar/news feed and a web-research provider.
- PostgreSQL deployment profile.
