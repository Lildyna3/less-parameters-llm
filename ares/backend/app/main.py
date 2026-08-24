"""ARES backend application.

Startup sequence (spec §65):
  load configuration → validate environment → detect MT5 → connect (verified)
  → database → market data service → analysis engine → AI services →
  WebSocket updates → ARES READY.

Every component reports its genuine state to the status registry; nothing is
marked ONLINE just because the process started.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from .ai.command import CommandCenter
from .ai.provider import AIProvider, build_provider
from .analysis.engine import AnalysisEngine
from .api.routes import router
from .api.ws import hub
from .config import AresConfig, get_config
from .database import Database
from .execution.baskets import BasketManager
from .execution.paper import PaperTradingEngine
from .execution.takeover import TakeoverManager
from .logging_setup import get_logger, setup_logging
from .market_data.providers import MT5Provider, SimulatedProvider
from .market_data.service import MarketDataService
from .mt5.adapter import MT5Adapter
from .mt5.monitor import MT5ConnectionMonitor
from .news.alerts import AlertManager
from .news.calendar import EconomicCalendar
from .risk.engine import RiskEngine
from .scanner.scanner import MarketScanner
from .status import ComponentState, status_registry

log = get_logger("main")


@dataclass
class AppServices:
    config: AresConfig
    mt5: MT5Adapter
    mt5_monitor: MT5ConnectionMonitor
    market_data: MarketDataService
    engine: AnalysisEngine
    scanner: MarketScanner
    risk: RiskEngine
    paper: PaperTradingEngine
    baskets: BasketManager
    takeover: TakeoverManager
    calendar: EconomicCalendar
    alerts: AlertManager
    db: Database
    command: CommandCenter
    ai_provider: AIProvider | None


def build_services(config: AresConfig) -> AppServices:
    mt5 = MT5Adapter(config.mt5)
    monitor = MT5ConnectionMonitor(mt5, config.mt5.reconnect_interval_seconds)

    if config.market_data.mode == "simulation":
        provider = SimulatedProvider()
        log.warning("Market data mode is SIMULATION — all prices are labeled SIMULATED, not live.")
    else:
        provider = MT5Provider(mt5)
    market_data = MarketDataService(provider, config.market_data)

    risk = RiskEngine(config.risk)
    paper = PaperTradingEngine(market_data, risk, config.execution)
    baskets = BasketManager(paper)
    takeover = TakeoverManager(paper, baskets, config.takeover)
    engine = AnalysisEngine(market_data, config.risk.max_spread_points)
    scanner = MarketScanner(engine)
    calendar = EconomicCalendar(config.news)
    alerts = AlertManager()
    db = Database(config.system.database_url)
    command = CommandCenter(market_data, engine, scanner, paper, baskets,
                            takeover, risk, calendar, provider=None)
    return AppServices(
        config=config, mt5=mt5, mt5_monitor=monitor, market_data=market_data,
        engine=engine, scanner=scanner, risk=risk, paper=paper, baskets=baskets,
        takeover=takeover, calendar=calendar, alerts=alerts, db=db,
        command=command, ai_provider=None,
    )


async def _periodic_engine_tick(svc: AppServices) -> None:
    """Marks paper positions to market, enforces basket max-loss, drives the
    takeover state machine, checks price alerts, and pushes account updates."""
    while True:
        try:
            await asyncio.sleep(1.0)
            await svc.paper.mark_to_market()
            breached = await svc.baskets.enforce_max_loss()
            for basket_id in breached:
                await svc.alerts.emit("risk", "danger",
                                      f"Basket {basket_id} hit its maximum loss and was closed")
            await svc.takeover.tick()
            await svc.alerts.check_price_alerts(svc.market_data.latest_ticks)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.error("engine tick error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config: AresConfig = app.state.config
    setup_logging(config.system.log_level)
    log.info("ARES START — environment=%s", config.environment)

    svc = build_services(config)
    app.state.services = svc

    # Execution status: paper always available; live intentionally absent.
    status_registry.set(
        "execution", ComponentState.ONLINE,
        "DEMO/PAPER mode — live trading is not available in this build",
        {"mode": "PAPER", "live_trading": False},
    )

    await svc.db.start()
    await svc.mt5_monitor.start()          # truthful connect attempt + monitor
    await svc.market_data.refresh_status()
    svc.market_data.broadcast = hub.broadcast
    svc.alerts.broadcast = hub.broadcast

    async def on_mt5_lost():
        await svc.alerts.emit("connection", "danger", "MT5 connection lost. Trading disabled.")
        await svc.market_data.refresh_status()

    async def on_mt5_restored():
        await svc.alerts.emit("connection", "info", "MT5 connection restored.")
        await svc.market_data.refresh_status()

    svc.mt5_monitor.on_connection_lost = on_mt5_lost
    svc.mt5_monitor.on_connection_restored = on_mt5_restored

    async def on_paper_update():
        await hub.broadcast({"type": "account", "data": svc.paper.account_snapshot()})

    async def on_trade_closed(trade):
        analysis = svc.command.last_analysis.get(trade.symbol)
        conditions = None
        if analysis:
            conditions = {"bias": analysis["bias"], "alignment": analysis["timeframe_alignment"],
                          "market_state": analysis["market_state"], "source": analysis["data_source"]}
        await svc.db.add_journal_entry(trade, market_conditions=conditions)
        await svc.alerts.emit(
            "execution", "info",
            f"Position {trade.id} closed ({trade.close_reason}): {trade.pl:+.2f}",
        )

    svc.paper.on_update = on_paper_update
    svc.paper.on_trade_closed = on_trade_closed

    svc.ai_provider = await build_provider(config.ai)
    svc.command.provider = svc.ai_provider

    await svc.market_data.start()
    engine_task = asyncio.create_task(_periodic_engine_tick(svc), name="engine-tick")

    status_registry.set("websocket", ComponentState.DEGRADED, "No clients connected")
    log.info("ARES READY — overall status %s", status_registry.overall.value)

    try:
        yield
    finally:
        engine_task.cancel()
        try:
            await engine_task
        except asyncio.CancelledError:
            pass
        await svc.market_data.stop()
        await svc.mt5_monitor.stop()
        await svc.db.stop()
        log.info("ARES shutdown complete")


def create_app(config: AresConfig | None = None) -> FastAPI:
    config = config or get_config()
    app = FastAPI(title="ARES", version="0.1.0",
                  description="Autonomous Real-time Execution & Strategy Intelligence",
                  lifespan=lifespan)
    app.state.config = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.system.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await hub.serve(ws)

    return app


app = create_app()
