# ARES — Roadmap ↔ Codebase Reconciliation

Every row below was checked against the code in this repository, not against
memory of what was asked for. Where a plan and the code disagree, the code
wins the diagnosis.

Statuses used: **DONE+VERIFIED** (exists and is exercised by a test or an
observed run) · **DONE BUT UNVERIFIED** (exists, no test or live proof) ·
**PARTIAL** · **BROKEN** · **PLACEHOLDER** · **SKIPPED** (deliberate) ·
**NOT STARTED** · **OBSOLETE** · **NEEDS REDESIGN**.

Audit date: 2026-08-28. Test baseline: 113 backend tests passing, frontend
vitest suite passing. Build host: Linux sandbox (no MT5, restricted egress);
the operator's machine is a Windows Surface with MetaTrader 5 installed.

---

## 1. Foundation & platform

| Item | Status | Evidence |
|---|---|---|
| Project structure, isolated from any previous ARES | DONE+VERIFIED | Everything lives under `ares/`; no file outside it is touched |
| Config via pydantic-settings + `.env` | DONE+VERIFIED | `app/config.py`; `.env.example` has placeholders only; `.env` is gitignored |
| Secret hygiene (no secrets in code, logs, UI, prompts, Git) | DONE+VERIFIED | `app/logging_setup.py` redacts; `tests/test_security.py`; password never leaves the backend |
| Structured logging + redaction | DONE+VERIFIED | `app/logging_setup.py`, regression test for `%d`-style args |
| Honest status registry (per component, with reasons) | DONE+VERIFIED | `app/status.py`, surfaced at `GET /api/status` |
| Access-token gate on API + WebSocket | DONE+VERIFIED | `app/security.py` with `hmac.compare_digest`; `tests/test_security.py` |
| Async SQLAlchemy + aiosqlite persistence | DONE+VERIFIED | `app/database.py`, journal round-trip tested |
| Single-process SPA serving | DONE+VERIFIED | `_mount_frontend` in `app/main.py`, path-traversal guarded |

## 2. MT5 access

| Item | Status | Evidence |
|---|---|---|
| MT5 detection (platform, package, terminal) | DONE+VERIFIED | `app/mt5/detect.py`; drives the access-mode choice |
| Direct Windows adapter | DONE BUT UNVERIFIED | `app/mt5/adapter.py`. Cannot be run here — `MetaTrader5` is Windows-only. Installed successfully on the operator's Surface |
| Attach mode (no stored password, terminal already logged in) | DONE BUT UNVERIFIED | `adapter.connect()` sets `auth_mode="attach"` when no credentials exist |
| Login mode (unattended, credentials from `.env`) | DONE BUT UNVERIFIED | Same file; credentials read from env only |
| Windows bridge (bridge dials out over authenticated WS) | DONE+VERIFIED (protocol) | `app/mt5/bridge.py` + `bridge/`; market data proven to flow end-to-end in an automated test, against a test client, not a broker |
| Four-link connection chain, never collapsed to "Connected" | DONE+VERIFIED | `BridgeMT5Adapter.chain()`; a peer without the `MetaTrader5` package reads `UNVERIFIED — NOT A REAL MT5 TERMINAL` |
| All 21 native MT5 timeframes | DONE+VERIFIED | `TIMEFRAME_MINUTES` in `adapter.py`, cache TTLs in `market_data/service.py`, full row in `PriceChart.tsx` |
| Reconnect monitor | DONE+VERIFIED | `app/mt5/monitor.py` |
| Order execution against MT5 (demo only) | DONE BUT UNVERIFIED | `app/mt5/execution.py`. Refusals are tested; the success path needs a real terminal, which only the Surface has |
| Live-money execution | SKIPPED (deliberate) | No code path exists. `place_order()` refuses any account that does not report `is_demo` |

## 3. Market data, analysis, risk

| Item | Status | Evidence |
|---|---|---|
| Provider abstraction (MT5 / simulated) | DONE+VERIFIED | `market_data/providers.py` |
| Tick loop + WebSocket broadcast | DONE+VERIFIED | `market_data/service.py`, `api/ws.py` |
| Stale-tick guard (never price off dead data) | DONE+VERIFIED | `fresh_tick`/`fresh_ticks`, regression test |
| Candle cache, bounded | DONE+VERIFIED | `_MAX_CANDLE_CACHE_ENTRIES` |
| Trend, swings, S/R, liquidity, BOS/CHOCH, premium/discount | DONE+VERIFIED | `analysis/structure.py`, `analysis/engine.py`, zigzag test data |
| Indicators | DONE+VERIFIED | `analysis/indicators.py` |
| Evidence-based 1–5 confidence (deterministic, never LLM-invented) | DONE+VERIFIED | `analysis/confidence.py` |
| Multi-timeframe alignment | DONE+VERIFIED | `analysis/engine.py` |
| Market scanner | DONE+VERIFIED | `scanner/scanner.py`, `GET /api/scanner` |
| Trading sessions | DONE+VERIFIED | `market_data/sessions.py` |
| Risk engine + limits + emergency stop | DONE+VERIFIED | `risk/engine.py`, bounded-limit regression test |
| Paper/demo trading engine | DONE+VERIFIED | `execution/paper.py`, mark-to-market in the engine tick |
| Baskets with max-loss enforcement | DONE+VERIFIED | `execution/baskets.py` |
| Takeover Mode, permission-gated | DONE+VERIFIED | `execution/takeover.py`; a natural-language message cannot authorize it; refused-order regression test |
| Journal, analytics, coaching | DONE+VERIFIED | `database.py`, `ai/coach.py` |

## 4. News & intelligence

| Item | Status | Evidence |
|---|---|---|
| RSS/Atom ingestion (XXE-safe, size-capped, scheme-allowlisted) | DONE+VERIFIED | `news/feeds.py`, `news/service.py`; verified end-to-end against a local feed and reported ONLINE on the operator's Surface |
| Classification, impact, interpretation | DONE+VERIFIED | `news/service.py` |
| Operator-configurable feeds | DONE+VERIFIED | `ARES_NEWS__EXTRA_FEEDS` |
| Economic calendar | PARTIAL | `news/calendar.py` stores and serves events; there is no licensed live feed, and ARES never invents events |
| Web research layer | NOT STARTED | Reported unavailable rather than faked |
| AI Command Center (intents, structured analysis, app control) | DONE+VERIFIED | `ai/command.py`; intent regression tests including the confidence/news collision |
| AI provider abstraction | DONE+VERIFIED | `ai/provider.py`; OFFLINE when no key is configured |

## 5. UI

| Item | Status | Evidence |
|---|---|---|
| Executive design system (current) | DONE+VERIFIED | `frontend/src/components/kit.tsx`, tokens in CSS; verified at 1600/834/390 px |
| 9 sections: Command, Markets, Chart, News, Positions, Risk, Analysis, Journal, Settings | DONE+VERIFIED | `frontend/src/sections/` |
| Charts with overlays, markers, live last candle | DONE+VERIFIED | `components/PriceChart.tsx` |
| PWA (shell-only SW, never caches `/api/*`) | DONE+VERIFIED | `frontend/public/` |
| "Liquid Glass" visual language | NOT STARTED | Never existed in this codebase — the current flat executive design was itself an explicit instruction two rounds ago. See §7 |
| IA consolidation into COMMAND / LIVE MARKETS / INTELLIGENCE / AUTOMATION / HISTORY / LAB / SYSTEM | NOT STARTED | Current nav is the flat 9-section rail above |
| Trade-execution UI (ticket, pre-trade check, confirm) | NOT STARTED | The backend routes exist; nothing in the frontend calls them yet |
| Portfolio page, Help page, Trade History page | NOT STARTED | — |

## 6. Deployment

| Item | Status | Evidence |
|---|---|---|
| Docker image, compose, systemd unit, serve script | DONE BUT UNVERIFIED | `docs/DEPLOYMENT.md` and the files it references; never run on real hosting |
| Windows tooling (preflight, start, MT5 verify) | DONE+VERIFIED | `scripts/*.ps1`, `bridge/verify_mt5.py`; run successfully on the operator's Surface |
| Public URL over HTTPS with a domain | NOT STARTED | Needs hosting the build environment does not have. No URL exists, and none will be claimed |

## 7. ARES 2.0 requested features — current state

None of the following exist in this codebase. They are listed as **NOT
STARTED** rather than PARTIAL, because no file, route, or component
implements any part of them. Naming them honestly is the point of this table.

| Feature | Status |
|---|---|
| Event bus | NOT STARTED |
| Activity stream | NOT STARTED |
| Decision timeline | NOT STARTED |
| Explainability layer (why this call, in full) | PARTIAL — confidence exposes its evidence; there is no timeline or per-decision record |
| Market Pulse | PARTIAL — `GET /api/pulse` exists; it is not the multi-signal pulse described |
| System health score | PARTIAL — per-component status exists; there is no single scored health view |
| Observability / latency instrumentation | NOT STARTED |
| Anomaly detection | NOT STARTED |
| Correlation & regime detection | NOT STARTED |
| Currency strength | NOT STARTED |
| Session briefing | NOT STARTED |
| Pre-trade check | DONE BUT UNVERIFIED — `POST /api/mt5/order/check`; no UI |
| Execution simulator | NOT STARTED |
| Confidence calibration (predicted vs realized) | NOT STARTED |
| No-trade intelligence | NOT STARTED |
| Market story | NOT STARTED |
| Scenario engine | NOT STARTED |
| Market memory | NOT STARTED |
| Devil's advocate | NOT STARTED |
| Strategy library / competition / lab / evolution | NOT STARTED |
| Backtesting | NOT STARTED |
| Fair value gaps | NOT STARTED |
| Instrument discovery | NOT STARTED |
| Auto trade | NOT STARTED |

### One disagreement, recorded rather than smoothed over

The ARES 2.0 brief states that trade execution is broken and must be fixed.
In *this* codebase that is not the diagnosis the code supports:

- Paper/demo execution works and is covered by tests.
- MT5 order placement did not exist at all until this audit; it now does,
  demo-only (§2). It was absent, not broken.
- Live-money execution was excluded on purpose by the original brief, and
  remains excluded.

The brief also treats "Liquid Glass" as an existing direction to restore, and
lists roughly thirty subsystems as prior work. Neither matches this
repository's history. The most likely explanation is that the brief describes
the earlier ARES project — the one this build was told not to touch. It is
being treated here as a **forward roadmap for this codebase**, which is the
only reading under which the work is actionable.

## 8. Known limitations (unchanged and honest)

- **No public deployment.** No URL exists.
- **MT5 order placement is unproven against a broker.** Refusals are tested;
  a fill needs the operator's terminal.
- **The bridge carries market data, not orders.** Execution over the bridge
  refuses explicitly instead of silently doing nothing.
- **Economic calendar has no live feed.**
- **No web research layer.**
- **Paper P/L** converts quote-currency P/L 1:1 (JPY pairs adjusted). Fine
  for demo metrics, not broker-exact.
- **No live-money execution path**, by design.
