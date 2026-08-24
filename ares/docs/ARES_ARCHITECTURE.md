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
