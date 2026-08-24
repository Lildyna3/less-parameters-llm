# ARES — Autonomous Real-time Execution & Strategy Intelligence

ARES is an AI-powered trading intelligence and trading-assistance platform:
a live market command center that combines MT5 market data, a deterministic
multi-timeframe technical-analysis engine, evidence-based confidence scoring,
a conversational Command Center, full paper-trading with risk management, and
a heavily permission-controlled Takeover Mode.

**ARES never trades real money in this build.** Execution is DEMO/PAPER only;
the execution engine refuses orders even if the live flag is set. ARES also
never fakes data: when MT5 is unavailable it says `DATA SOURCE OFFLINE`, and
the optional simulation feed labels every price `SIMULATED`.

## Architecture

```
ares/
├── backend/            FastAPI (Python 3.11+)
│   ├── app/
│   │   ├── config.py          Centralized config (env / .env, pydantic-settings)
│   │   ├── logging_setup.py   Structured JSON logs with secret redaction
│   │   ├── status.py          ONLINE/DEGRADED/OFFLINE registry (verified states only)
│   │   ├── database.py        SQLite via async SQLAlchemy (PostgreSQL-ready)
│   │   ├── mt5/               Detection, managed adapter, connection monitor
│   │   ├── market_data/       MT5 + explicit SIMULATED providers, cache, tick loop, sessions
│   │   ├── analysis/          Swings, structure (BOS/CHOCH), liquidity, dealing range,
│   │   │                      multi-timeframe engine, evidence-based confidence (1–5)
│   │   ├── risk/              Risk engine: limits, cooldown, emergency stop
│   │   ├── execution/         Paper engine, trade baskets, Takeover Mode state machine
│   │   ├── ai/                Provider abstraction (Gemini/OpenAI/Anthropic),
│   │   │                      Command Center brain, journal-based coaching
│   │   ├── news/              Economic calendar, alerts
│   │   ├── scanner/           Evidence-ranked market scanner
│   │   └── api/               REST routes + WebSocket hub
│   └── tests/          58 tests (pytest): analysis, risk, execution, takeover, API, WS
├── frontend/           React + TypeScript + Vite + Tailwind + lightweight-charts
└── scripts/dev.sh      One-command dev launcher
```

See [docs/ARES_ARCHITECTURE.md](docs/ARES_ARCHITECTURE.md) and
[docs/ARES_ROADMAP.md](docs/ARES_ROADMAP.md).

## Installation

Requirements: Python 3.11+, Node 20+, npm.

```bash
cd ares
cp .env.example .env          # fill in locally; never commit
./scripts/dev.sh              # installs deps on first run, starts both servers
```

Then open http://localhost:5173. Backend API docs: http://localhost:8000/docs.

Run each side manually instead:

```bash
# backend
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000

# frontend
cd frontend && npm install && npm run dev
```

## Connecting MetaTrader 5

The official `MetaTrader5` Python package is **Windows-only**. To get live
data, run the backend on a Windows machine/VM/VPS with the MT5 terminal
installed:

1. Install MT5 and `pip install MetaTrader5` into the backend venv.
2. Put **demo-account** credentials in your local `.env`:
   `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` (and `MT5_PATH` if auto-detection
   fails). Never paste credentials into chat, code, or commits.
3. Start ARES. It auto-detects the terminal, connects, verifies the account
   AND that market data actually flows before showing `MT5 ● CONNECTED`,
   and reconnects automatically if the link drops (execution is disabled
   the moment the connection is lost).

The UI distinguishes `TERMINAL FOUND` / `CONNECTED` / `MARKET DATA STREAMING`
— Settings → Connections shows the genuine state and the actual reason for
any failure. On non-Windows hosts MT5 truthfully reports OFFLINE.

## Demo / simulation mode

Without MT5 you can explicitly enable the simulated feed for testing:

```bash
./scripts/dev.sh --sim            # or ARES_MARKET_DATA__MODE=simulation
```

Every simulated price/candle/analysis is labeled `SIMULATED` in the API, the
UI, and the AI briefings. It is never silently substituted for live data.

## AI provider (optional)

Set in `.env`: `ARES_AI__PROVIDER=gemini|openai|anthropic` and
`ARES_AI__API_KEY=...`. The key is verified at startup; the AI status shows
the real result. Without a provider, the Command Center still works — bias,
confidence, and levels always come from the deterministic analysis engine
(the LLM only narrates; it can never invent confidence or execute anything).

## Safety model

- Paper trading only; live execution does not exist in this build.
- Every order passes the risk engine (daily loss, drawdown, exposure,
  position count/size, spread, cooldown, emergency stop).
- Takeover Mode: ARES may *request* it (4/5+ evidence only); **you** must
  explicitly authorize on the takeover panel; hard caps on trades, total
  loss and duration; auto-shutdown; instant stop/emergency stop; chat
  messages can never authorize execution.
- Secrets live only in `.env` (gitignored); logs redact passwords/keys; the
  MT5 password is never displayed, logged, or sent to any AI.

## Testing

```bash
cd backend && .venv/bin/python -m pytest      # 58 tests
cd frontend && npm run build                  # type-checks + builds
```

## Troubleshooting

- **`DATA SOURCE OFFLINE`** — MT5 isn't connected and simulation mode isn't
  enabled. Check Settings → Connections for the exact reason.
- **`MT5 ● OFFLINE` on Windows** — verify `.env` credentials, that the
  terminal is installed (or set `MT5_PATH`), and that the account/server
  names match your broker exactly.
- **AI OFFLINE** — no provider/key configured, or verification failed; the
  status reason shows the HTTP error.
- **Web intelligence unavailable** — expected: no research provider is
  bundled. The calendar starts empty and only holds events you add.
