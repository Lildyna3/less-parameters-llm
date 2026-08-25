"""REST API routes. All routes read from the shared AppServices container
attached to app.state.services in main.py."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..ai.coach import coach_from_journal
from ..market_data.sessions import current_sessions
from ..status import status_registry

router = APIRouter(prefix="/api")


def services(request: Request):
    return request.app.state.services


# ---- schemas -----------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    symbol: str = Field(min_length=3, max_length=16)


class CommandRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class OrderRequest(BaseModel):
    symbol: str
    direction: str
    volume: float = Field(gt=0)
    sl: float | None = None
    tp: float | None = None
    strategy: str | None = None
    confidence: int | None = Field(default=None, ge=1, le=5)
    basket_id: str | None = None


class ClosePositionRequest(BaseModel):
    position_id: str


class TakeoverRequestBody(BaseModel):
    symbol: str
    direction: str
    reason: str
    confidence: int = Field(ge=1, le=5)
    proposed_trades: list[dict]
    max_loss: float | None = None
    duration_seconds: int | None = None


class TakeoverAuthorizeBody(BaseModel):
    session_id: str
    confirm: bool = False


class CalendarEventBody(BaseModel):
    title: str
    currency: str
    impact: str
    scheduled_at: str
    previous: str | None = None
    forecast: str | None = None
    actual: str | None = None


class PriceAlertBody(BaseModel):
    symbol: str
    level: float
    condition: str  # above | below
    note: str | None = None


class RiskUpdateBody(BaseModel):
    # Bounds keep the risk engine coherent: zero/negative limits would either
    # disable protection or block every order with a misleading reason.
    max_daily_loss: float | None = Field(default=None, gt=0)
    max_drawdown_percent: float | None = Field(default=None, gt=0, le=100)
    max_open_positions: int | None = Field(default=None, ge=1)
    max_exposure_lots: float | None = Field(default=None, gt=0)
    max_trades_per_session: int | None = Field(default=None, ge=1)
    max_position_size_lots: float | None = Field(default=None, gt=0)
    max_spread_points: float | None = Field(default=None, gt=0)
    cooldown_seconds_after_loss: float | None = Field(default=None, ge=0)


# ---- system --------------------------------------------------------------------

@router.get("/health")
async def health():
    return {"status": "ok", "app": "ARES", "components": status_registry.snapshot(),
            "overall": status_registry.overall.value}


@router.get("/status")
async def system_status():
    return {"components": status_registry.snapshot(), "overall": status_registry.overall.value,
            "sessions": current_sessions()}


@router.get("/account")
async def account(request: Request):
    svc = services(request)
    payload = {"paper": svc.paper.account_snapshot(), "mt5": svc.mt5.status_payload()}
    return payload


# ---- market data ------------------------------------------------------------------

@router.get("/symbols")
async def symbols(request: Request):
    svc = services(request)
    data = await svc.market_data.get_symbols()
    if not data:
        return {"symbols": [], "source": None,
                "message": "DATA SOURCE OFFLINE — no symbols available"}
    return {"symbols": data, "source": svc.market_data.source_label}


@router.get("/watchlist")
async def watchlist(request: Request):
    svc = services(request)
    return {"symbols": svc.market_data.watched_symbols}


@router.post("/watchlist/{symbol}")
async def watchlist_add(symbol: str, request: Request):
    svc = services(request)
    symbol = symbol.upper()
    if symbol in svc.market_data.watched_symbols:
        return {"symbols": svc.market_data.watched_symbols, "added": False}
    # Verify the symbol actually exists at the provider before watching it.
    tick = await svc.market_data.get_tick(symbol)
    if tick is None:
        raise HTTPException(
            404, detail=f"Symbol {symbol} is not available from the current data source")
    if symbol not in svc.market_data.watched_symbols:
        svc.market_data.watched_symbols.append(symbol)
    return {"symbols": svc.market_data.watched_symbols, "added": True}


@router.delete("/watchlist/{symbol}")
async def watchlist_remove(symbol: str, request: Request):
    svc = services(request)
    symbol = symbol.upper()
    if symbol not in svc.market_data.watched_symbols:
        raise HTTPException(404, detail=f"{symbol} is not on the watchlist")
    svc.market_data.watched_symbols.remove(symbol)
    svc.market_data.latest_ticks.pop(symbol, None)
    return {"symbols": svc.market_data.watched_symbols, "removed": True}


@router.get("/market/{symbol}")
async def market(symbol: str, request: Request):
    svc = services(request)
    tick = await svc.market_data.get_tick(symbol.upper())
    if tick is None:
        raise HTTPException(503, detail=f"DATA SOURCE OFFLINE — no market data for {symbol}")
    return tick


@router.get("/candles/{symbol}")
async def candles(symbol: str, request: Request, timeframe: str = "M15", count: int = 300):
    svc = services(request)
    count = max(10, min(count, 1500))
    data = await svc.market_data.get_candles(symbol.upper(), timeframe.upper(), count)
    if not data:
        raise HTTPException(503, detail=f"DATA SOURCE OFFLINE — no candles for {symbol} {timeframe}")
    return {"symbol": symbol.upper(), "timeframe": timeframe.upper(),
            "source": svc.market_data.source_label, "candles": data}


# ---- analysis / AI -------------------------------------------------------------------

@router.post("/analyze")
async def analyze(body: AnalyzeRequest, request: Request):
    svc = services(request)
    news = svc.calendar.news_risk_for(body.symbol.upper())
    analysis = await svc.engine.analyze(body.symbol.upper(), news_risk=news is not None)
    if analysis is None:
        raise HTTPException(503, detail="DATA SOURCE OFFLINE — cannot analyze without market data")
    svc.command.remember(analysis)
    return {"analysis": analysis, "news_warning": news}


@router.post("/command")
async def command(body: CommandRequest, request: Request):
    svc = services(request)
    return await svc.command.handle(body.message)


@router.get("/scanner")
async def scanner(request: Request):
    svc = services(request)
    rows = await svc.scanner.scan(svc.market_data.watched_symbols[:12])
    return {"results": rows, "source": svc.market_data.source_label if rows else None}


# ---- paper trading --------------------------------------------------------------------

@router.get("/positions")
async def positions(request: Request):
    svc = services(request)
    return {"positions": [p.as_dict() for p in svc.paper.positions.values()],
            "baskets": svc.baskets.list_views()}


@router.get("/trades")
async def trades(request: Request, limit: int = 100):
    svc = services(request)
    return {"trades": [t.as_dict() for t in reversed(svc.paper.history[-limit:])]}


@router.post("/order/validate")
async def order_validate(body: OrderRequest, request: Request):
    svc = services(request)
    result = await svc.paper.validate_order(body.symbol.upper(), body.direction, body.volume, body.sl, body.tp)
    return result.as_dict()


@router.post("/order/demo")
async def order_demo(body: OrderRequest, request: Request):
    svc = services(request)
    result = await svc.paper.submit_order(
        body.symbol.upper(), body.direction, body.volume, body.sl, body.tp,
        strategy=body.strategy, confidence=body.confidence, basket_id=body.basket_id,
    )
    if not result.success:
        return result.as_dict()
    await svc.alerts.emit("execution", "info",
                          f"Demo order filled: {body.direction} {body.symbol.upper()} {body.volume} lots")
    return result.as_dict()


@router.post("/position/close")
async def position_close(body: ClosePositionRequest, request: Request):
    svc = services(request)
    result = await svc.paper.close_position(body.position_id)
    return result.as_dict()


@router.post("/basket/{basket_id}/close")
async def basket_close(basket_id: str, request: Request):
    svc = services(request)
    return await svc.baskets.close_basket(basket_id)


# ---- risk ----------------------------------------------------------------------------------

@router.get("/risk")
async def risk(request: Request):
    return services(request).risk.snapshot()


@router.post("/risk/limits")
async def risk_limits(body: RiskUpdateBody, request: Request):
    svc = services(request)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    for key, value in updates.items():
        setattr(svc.risk.settings, key, value)
    return {"updated": updates, "risk": svc.risk.snapshot()}


@router.post("/risk/emergency-stop")
async def emergency_stop(request: Request):
    svc = services(request)
    svc.risk.engage_emergency_stop("API request")
    closed = await svc.paper.emergency_close_all()
    await svc.takeover.stop(reason="emergency stop")
    await svc.alerts.emit("risk", "danger", "EMERGENCY STOP engaged — all execution blocked")
    return {"engaged": True, "closed": closed}


@router.post("/risk/emergency-stop/release")
async def emergency_release(request: Request):
    svc = services(request)
    svc.risk.release_emergency_stop()
    return {"engaged": False}


# ---- takeover --------------------------------------------------------------------------------

@router.get("/takeover")
async def takeover_status(request: Request):
    return services(request).takeover.status()


@router.post("/takeover/request")
async def takeover_request(body: TakeoverRequestBody, request: Request):
    svc = services(request)
    return svc.takeover.request(**body.model_dump())


@router.post("/takeover/authorize")
async def takeover_authorize(body: TakeoverAuthorizeBody, request: Request):
    if not body.confirm:
        raise HTTPException(400, detail="Explicit confirmation required: set confirm=true. "
                                        "Takeover cannot be authorized implicitly.")
    svc = services(request)
    result = svc.takeover.authorize(body.session_id)
    if result["success"]:
        await svc.alerts.emit("execution", "warning",
                              f"Takeover session {body.session_id} AUTHORIZED by user")
    return result


@router.post("/takeover/stop")
async def takeover_stop(request: Request):
    svc = services(request)
    result = await svc.takeover.stop(reason="user stop via API")
    await svc.alerts.emit("execution", "warning", "Takeover stopped by user")
    return result


# ---- journal / analytics / coaching -----------------------------------------------------------

@router.get("/journal")
async def journal(request: Request, limit: int = 200, symbol: str | None = None):
    svc = services(request)
    return {"entries": await svc.db.journal_entries(limit=limit, symbol=symbol)}


class JournalNotesBody(BaseModel):
    notes: str = Field(max_length=2000)


@router.patch("/journal/{entry_id}/notes")
async def journal_notes(entry_id: int, body: JournalNotesBody, request: Request):
    svc = services(request)
    entry = await svc.db.update_journal_notes(entry_id, body.notes)
    if entry is None:
        raise HTTPException(404, detail=f"Journal entry {entry_id} not found")
    return {"entry": entry}


@router.get("/coach")
async def coach(request: Request):
    svc = services(request)
    entries = await svc.db.journal_entries(limit=100)
    return coach_from_journal(entries)


@router.get("/analytics")
async def analytics(request: Request):
    svc = services(request)
    account_snapshot = svc.paper.account_snapshot()
    confidences = [t.confidence for t in svc.paper.history if t.confidence]
    dist: dict[int, int] = {}
    for c in confidences:
        dist[c] = dist.get(c, 0) + 1
    return {
        "account": account_snapshot,
        "ares": {
            "analyses_performed": svc.engine.analyses_performed,
            "risk_blocks": svc.risk.blocks_issued,
            "confidence_distribution": dist,
            "successful_setups": len([t for t in svc.paper.history if t.pl > 0 and (t.confidence or 0) >= 4]),
            "failed_setups": len([t for t in svc.paper.history if t.pl < 0 and (t.confidence or 0) >= 4]),
        },
    }


# ---- news / calendar / alerts ---------------------------------------------------------------------

@router.get("/calendar")
async def calendar(request: Request, hours: float = 48):
    svc = services(request)
    return {"events": svc.calendar.upcoming(hours=hours),
            "note": "Calendar starts empty; add events manually or connect a licensed feed. ARES never fabricates news."}


@router.post("/calendar/events")
async def calendar_add(body: CalendarEventBody, request: Request):
    svc = services(request)
    try:
        event = svc.calendar.add_event(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc))
    return {"event": event.as_dict()}


@router.get("/alerts")
async def alerts(request: Request):
    return services(request).alerts.list_state()


@router.post("/alerts/price")
async def alerts_add(body: PriceAlertBody, request: Request):
    svc = services(request)
    if body.condition not in ("above", "below"):
        raise HTTPException(400, detail="condition must be 'above' or 'below'")
    return {"alert": svc.alerts.add_price_alert(body.symbol, body.level, body.condition, body.note)}


@router.delete("/alerts/price/{alert_id}")
async def alerts_delete(alert_id: int, request: Request):
    removed = services(request).alerts.remove_price_alert(alert_id)
    if not removed:
        raise HTTPException(404, detail="alert not found")
    return {"removed": alert_id}
