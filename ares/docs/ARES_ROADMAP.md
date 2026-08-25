# ARES Roadmap & Phase Status

Build environment: Linux host, Python 3.11.15, Node 22, npm 10.9.7.
The dependency-installation blocker reported for Phase 1 does not exist in
this environment — pip and npm registries were verified reachable before
building, and all installs completed normally.

| Phase | Scope | Status | Notes |
|---|---|---|---|
| 1 | Foundation (project structure, config, .env protection, logging, status registry, health endpoint, MT5 detection) | **COMPLETE** | Backend starts; `/api/health` verified live; MT5 truthfully OFFLINE on Linux (Windows-only package); secrets redacted in logs; tests pass |
| 2 | UI shell (new design direction — replaces the original UI concept) | **COMPLETE** | Dark-first design system, rail nav, top status bar, persisted theme, mounted-section state preservation, mobile layout |
| 3 | Market data (MT5 provider, explicit SIMULATED provider, tick loop, caching, WS) | **COMPLETE** | `DATA SOURCE OFFLINE` when nothing real is available; SIMULATED labeled everywhere |
| 4 | Charts (candlesticks, 7 timeframes, volume, crosshair, zoom/pan, live updates, overlays) | **COMPLETE** | lightweight-charts v5; chart instance preserved across navigation; trade + level overlays |
| 5 | Technical analysis (trend, swings, S/R, liquidity/sweeps, BOS/CHOCH, premium/discount, volatility) | **COMPLETE** | Deterministic, evidence + confidence, unit-tested |
| 6 | AI Command Center (intents, structured analysis, follow-ups, app control actions) | **COMPLETE** | LLM optional (Gemini/OpenAI/Anthropic, verified at startup); deterministic narrator fallback; chat can never authorize execution |
| 7 | MT5 integration (managed adapter, auto-connect flow, verification, monitor, settings UI) | **COMPLETE (code)** / **UNVERIFIABLE ON THIS HOST** | The MetaTrader5 package is Windows-only; the full connect path needs a Windows+MT5 host to exercise. Offline/degraded paths are tested |
| 8 | Demo/paper trading (validate, fill, SL/TP, history, account metrics) | **COMPLETE** | Fills at real bid/ask of the active source; refuses without data |
| 9 | Risk management (limits, cooldown, emergency stop, spread protection) | **COMPLETE** | Blocking, auditable, configurable from Settings |
| 10 | Market scanner | **COMPLETE** | Evidence-ranked table, click-through to chart |
| 11 | News / web intelligence | **COMPLETE (honest-minimal)** | Calendar holds only user/licensed events — never fabricated; web research truthfully "unavailable" until a provider is wired |
| 12 | Trade journal + analytics + coaching | **COMPLETE** | SQLite journal, behavior-based coach, analytics dashboard |
| 13 | Takeover Mode | **COMPLETE** | Request→explicit authorize→hard-capped execution→auto shutdown; baskets; instant stop |
| 14 | Performance | **COMPLETE** | TTL caches, one WS, memoized store updates, mounted sections, ~130 KB gzip bundle |
| 15 | Security + testing | **COMPLETE** | .env-only secrets, log redaction, masked account, 62 backend tests + 14 vitest component/store tests + tsc build + Playwright smoke |
| 16 | Final polish | **COMPLETE** | Light theme, mobile layout, docs, one-command launcher |

## Known limitations

- Live MT5 connection requires a Windows host; on other platforms the MT5
  component is truthfully OFFLINE and only simulation mode provides data.
- Paper P/L converts quote-currency P/L 1:1 to the account currency
  (JPY pairs adjusted); good enough for demo metrics, not broker-exact.
- Economic calendar has no live feed; web intelligence has no provider.

## Next steps

1. Exercise the MT5 layer on a Windows demo account end-to-end.
2. Wire a licensed calendar/news feed and a web-research provider.
3. PostgreSQL profile + deployment hardening for multi-user use.
