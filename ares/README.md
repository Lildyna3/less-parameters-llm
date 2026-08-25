# ARES — Autonomous Real-time Execution & Strategy Intelligence

A private executive trading command center: live market data, a deterministic
multi-timeframe analysis engine, evidence-based confidence, a professional news
feed, paper trading with a blocking risk engine, and permission-gated
autonomous execution — reachable from your phone and laptop at one URL.

**Two rules the whole system is built around:**

1. **Nothing is fabricated.** Prices, news, account data, MT5 status and
   execution results are either real or explicitly reported as unavailable.
   There is no placeholder that could be mistaken for data.
2. **Connection is never permission.** Live-money execution does not exist in
   this build. Every order passes the risk engine, and autonomous execution
   needs your explicit authorization with hard caps.

## Quick start

```bash
cd ares
cp .env.example .env          # fill in locally; never commit

docker compose up -d --build  # production: one process, one URL
# or, without Docker:
./scripts/serve.sh            # builds the web app, then serves it

# development, two processes with hot reload:
./scripts/dev.sh --sim
```

Open `http://localhost:8000` (or `http://<lan-ip>:8000` from your phone).
Deployment, HTTPS and PWA install: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Without a broker connection, `--sim` / `ARES_MARKET_DATA__MODE=simulation`
gives a labelled simulated feed for exploring the system. Every simulated
value is tagged `SIMULATED` in the API, the UI and ARES's own commentary.

## The interface

| Area | What it is |
|---|---|
| **Command** | The workspace: market pulse (regime, volatility, session, movers, next event), live chart, strongest evidence, headlines, and the ARES intelligence feed with its command line (⌘K) |
| **Markets** | Every instrument the data source offers — search, favourites, asset-class filters, watchlist management |
| **Chart** | The market workspace: chart with levels, entries, stops and targets, plus the paper order ticket and price alerts |
| **News** | Chronological professional feed with category filters, a reading view, ARES's interpretation, and a direct route into any mentioned instrument's analysis |
| **Positions** | Open positions with contextual detail, trade baskets, takeover control, recent closes |
| **Risk** | Daily P/L, loss remaining, drawdown, exposure, utilisation against every limit, emergency stop |
| **Analysis** | The full structured read — timeframes, structure, liquidity, levels, scenarios, invalidation, and why the confidence score is what it is — plus the market scanner |
| **Journal** | Every recorded trade with notes, performance figures, and coaching drawn only from recorded behaviour |
| **Settings** | Nine-section configuration centre: general, connections, trading, risk, AI, notifications, interface, security, system |

## Architecture

```
ares/
├── backend/            FastAPI · Python 3.11+
│   └── app/
│       ├── config.py        every setting, from env/.env
│       ├── status.py        ONLINE/DEGRADED/OFFLINE, verified only
│       ├── security.py      optional access token for API + WebSocket
│       ├── mt5/             detection, direct adapter, bridge server, monitor
│       ├── market_data/     providers, cache, tick loop, sessions
│       ├── analysis/        structure, multi-timeframe engine, confidence
│       ├── risk/            blocking limits, cooldown, emergency stop
│       ├── execution/       paper engine, baskets, takeover state machine
│       ├── ai/              provider abstraction, command centre, coaching
│       ├── news/            RSS ingestion, classification, calendar, alerts
│       └── api/             REST routes + WebSocket hub
├── frontend/           React · TypeScript · Vite · Tailwind · lightweight-charts
├── bridge/             the Windows MT5 bridge (runs beside MetaTrader 5)
├── Dockerfile          one image: builds the web app, serves everything
└── docs/               architecture, roadmap, MT5 bridge, deployment
```

Details: [docs/ARES_ARCHITECTURE.md](docs/ARES_ARCHITECTURE.md).

## MetaTrader 5

The `MetaTrader5` Python package wraps the **Windows** terminal's IPC and has
no Linux build, so a cloud backend can never drive MT5 directly. ARES solves
this with a bridge: a small process runs on a Windows machine beside the
terminal and dials **out** to your backend over an authenticated WebSocket, so
Windows needs no open ports.

Until that bridge attaches *and* its terminal reports a live broker connection,
ARES shows MT5 as offline with the real reason. States are precise:
`DISCONNECTED`, `CONNECTING`, `CONNECTED`, `ERROR`, `MT5 TERMINAL NOT RUNNING`,
`BROKER DISCONNECTED`, `AUTHENTICATION REQUIRED`.

Setup and how to verify the connection is genuine:
[docs/MT5_BRIDGE.md](docs/MT5_BRIDGE.md).

On Windows, ARES skips the bridge and drives the terminal directly.

## News

Real RSS/Atom ingestion from public financial sources (ForexLive, FXStreet,
Investing.com, MarketWatch, CNBC, Cointelegraph). Headlines, summaries, sources
and timestamps are reproduced verbatim; ARES adds keyword-derived instrument
and currency tagging, a LOW/MODERATE/HIGH/CRITICAL impact score, and its own
interpretation — always in a separate, labelled block.

If the host cannot reach those sources, the feed is empty and says exactly
that, per source. ARES never writes a headline.

Add your own feeds with `ARES_NEWS__EXTRA_FEEDS` (JSON), or replace the
built-in list entirely with `ARES_NEWS__REPLACE_DEFAULT_FEEDS=true`.

## Safety model

- Paper trading only; there is no live execution path in this build.
- Every order is checked against daily loss, drawdown, open positions,
  exposure, trades per session, position size, spread, and post-loss cooldown.
- Orders are priced from a fresh quote; a stale quote refuses the order rather
  than filling at an old price.
- Takeover Mode: ARES may *request* at 4/5 evidence or better; you authorize
  explicitly; hard caps on trades, total loss and duration; auto-shutdown;
  instant stop. A chat message can never authorize execution.
- Secrets live in the environment only. The MT5 password never leaves the
  bridge machine, is never logged, never displayed, and never sent to any AI.

## Testing

```bash
cd backend  && .venv/bin/python -m pytest    # 104 tests
cd frontend && npm test                      # 19 tests
cd frontend && npm run build                 # type-check + production build
```

## Troubleshooting

| Symptom | Meaning |
|---|---|
| `DATA SOURCE OFFLINE` | no MT5 bridge attached and simulation is off — see Settings → Connections |
| `NEWS UNAVAILABLE` | this host cannot reach the news sources; ARES shows nothing rather than inventing |
| `MT5 · AUTHENTICATION REQUIRED` | `ARES_BRIDGE_TOKEN` is unset on the server |
| `MT5 · MT5 TERMINAL NOT RUNNING` | the bridge is connected but the terminal is closed |
| AI `OFFLINE` | no provider/key configured, or key verification failed — analysis still works |
| 401 from the API | this deployment requires `ARES_ACCESS_TOKEN`; enter it when prompted |
