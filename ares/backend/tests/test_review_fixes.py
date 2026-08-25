"""Regression tests for the code-review findings (round 3)."""

import time as time_module

import pytest
from fastapi.testclient import TestClient

from app.ai.command import CommandCenter
from app.analysis.engine import AnalysisEngine
from app.config import NewsSettings, TakeoverSettings
from app.execution.baskets import BasketManager
from app.execution.takeover import TakeoverManager, TakeoverState
from app.main import create_app
from app.news.calendar import EconomicCalendar, parse_when
from app.scanner.scanner import MarketScanner


@pytest.fixture
def client(test_config):
    app = create_app(test_config)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def command(market_data, paper, risk) -> CommandCenter:
    engine = AnalysisEngine(market_data)
    baskets = BasketManager(paper)
    takeover = TakeoverManager(paper, baskets, TakeoverSettings())
    return CommandCenter(
        market_data, engine, MarketScanner(engine), paper, baskets,
        takeover, risk, EconomicCalendar(NewsSettings()),
    )


# -- finding 1: stale tick cache ------------------------------------------------

@pytest.mark.asyncio
async def test_stale_ticks_are_not_served(market_data):
    tick = await market_data.get_tick("EURUSD")
    assert tick is not None
    # Age the cached tick beyond the freshness window.
    market_data._tick_times["EURUSD"] = time_module.monotonic() - 3600
    assert market_data.fresh_tick("EURUSD") is None
    assert "EURUSD" not in market_data.fresh_ticks()
    # get_tick refetches from the provider instead of serving the stale one.
    refreshed = await market_data.get_tick("EURUSD")
    assert refreshed is not None
    assert market_data.fresh_tick("EURUSD") is not None


@pytest.mark.asyncio
async def test_mark_to_market_ignores_stale_prices(paper):
    tick = await paper.market_data.get_tick("EURUSD")
    result = await paper.submit_order("EURUSD", "buy", 0.1, sl=tick["ask"] - 0.005, tp=None)
    assert result.success, result.message
    pos = list(paper.positions.values())[0]
    # A stale tick far below SL must not trigger the stop.
    paper.market_data._store_tick("EURUSD", {
        "symbol": "EURUSD", "bid": 0.5, "ask": 0.50008,
        "spread_points": 2, "source": "SIMULATED",
    })
    paper.market_data._tick_times["EURUSD"] = time_module.monotonic() - 3600
    await paper.mark_to_market()
    assert pos.id in paper.positions, "stale price must not trigger SL"


# -- finding 2: calendar naive datetimes ------------------------------------------

def test_calendar_accepts_naive_timestamps_as_utc():
    cal = EconomicCalendar(NewsSettings())
    from datetime import datetime, timedelta, timezone
    naive = (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(tzinfo=None)
    cal.add_event(title="CPI", currency="USD", impact="high",
                  scheduled_at=naive.isoformat())  # no offset
    # Neither call raises, and the event is found.
    assert cal.upcoming()
    warning = cal.news_risk_for("EURUSD")
    assert warning is not None


def test_calendar_rejects_garbage_timestamp(client):
    resp = client.post("/api/calendar/events", json={
        "title": "X", "currency": "USD", "impact": "high", "scheduled_at": "not-a-date"})
    assert resp.status_code == 422


def test_parse_when_helper():
    assert parse_when("2026-08-26T14:30:00").tzinfo is not None
    assert parse_when("2026-08-26T14:30:00Z") is not None
    assert parse_when("garbage") is None


# -- finding 3: symbol extraction overmatch ------------------------------------------

@pytest.mark.asyncio
async def test_ordinary_words_are_not_symbols(command):
    assert command._extract_symbol("what should I trade today") is None
    assert command._extract_symbol("show me the market") is None
    resp = await command.handle("what should I trade today")
    assert "SHOULD" not in resp["reply"]


@pytest.mark.asyncio
async def test_real_symbols_still_extracted(command):
    assert command._extract_symbol("analyze eurusd") == "EURUSD"
    assert command._extract_symbol("Analyze GOLD please") == "XAUUSD"
    assert command._extract_symbol("open GBPJPY H1") == "GBPJPY"


@pytest.mark.asyncio
async def test_scan_requires_word_boundary(command):
    resp = await command.handle("tell me about the scandal")
    assert "Scanned" not in resp["reply"]


# -- finding 4: takeover input validation ----------------------------------------------

def test_takeover_request_rejects_malformed_trades(takeover):
    result = takeover.request(symbol="EURUSD", direction="buy", reason="r", confidence=4,
                              proposed_trades=[{"symbol": "EURUSD"}])
    assert not result["success"]
    assert "missing required field" in result["message"]

    result = takeover.request(symbol="EURUSD", direction="buy", reason="r", confidence=4,
                              proposed_trades=[{"symbol": "EURUSD", "direction": "buy",
                                                "volume": "lots", "sl": 1.0}])
    assert not result["success"]
    assert "non-numeric" in result["message"]


def test_takeover_request_api_returns_clean_error(client):
    resp = client.post("/api/takeover/request", json={
        "symbol": "EURUSD", "direction": "buy", "reason": "r", "confidence": 4,
        "proposed_trades": [{"symbol": "EURUSD"}]})
    assert resp.status_code == 200
    assert resp.json()["success"] is False


# -- finding 6: risk limit bounds -----------------------------------------------------------

def test_risk_limits_reject_nonpositive_values(client):
    assert client.post("/api/risk/limits", json={"max_daily_loss": -100}).status_code == 422
    assert client.post("/api/risk/limits", json={"max_position_size_lots": 0}).status_code == 422
    assert client.post("/api/risk/limits", json={"max_drawdown_percent": 150}).status_code == 422
    assert client.post("/api/risk/limits", json={"max_daily_loss": 250}).status_code == 200


# -- finding 7: takeover completion honesty -----------------------------------------------------

@pytest.mark.asyncio
async def test_all_refused_takeover_is_not_completed(takeover, paper, risk):
    result = takeover.request(
        symbol="EURUSD", direction="buy", reason="r", confidence=4,
        proposed_trades=[{"symbol": "EURUSD", "direction": "buy", "volume": 0.05,
                          "sl": 1.0, "tp": 1.2}])
    takeover.authorize(result["session"]["id"])
    risk.engage_emergency_stop("test")  # every order will be refused
    await takeover.tick()
    assert takeover.session is None or takeover.session.state != TakeoverState.ACTIVE
    archived = takeover.history[-1]
    assert archived["state"] == "STOPPED"
    assert archived["trades_executed"] == 0
    assert any("all refused" in line.lower() for line in archived["log"])


# -- finding 8: candle cache bound -----------------------------------------------------------------

# -- new endpoints: watchlist + journal notes -------------------------------------------------

def test_watchlist_add_remove(client):
    base = client.get("/api/watchlist").json()["symbols"]
    assert "EURUSD" in base

    added = client.post("/api/watchlist/BTCUSD").json()
    assert added["added"] is True and "BTCUSD" in added["symbols"]
    # idempotent
    again = client.post("/api/watchlist/BTCUSD").json()
    assert again["added"] is False

    unknown = client.post("/api/watchlist/NOSUCH1")
    assert unknown.status_code == 404

    removed = client.delete("/api/watchlist/BTCUSD").json()
    assert removed["removed"] is True and "BTCUSD" not in removed["symbols"]
    assert client.delete("/api/watchlist/BTCUSD").status_code == 404


def test_journal_notes_update(client):
    order = client.post("/api/order/demo", json={
        "symbol": "EURUSD", "direction": "buy", "volume": 0.05}).json()
    client.post("/api/position/close", json={"position_id": order["position"]["id"]})
    entry = client.get("/api/journal").json()["entries"][0]

    resp = client.patch(f"/api/journal/{entry['id']}/notes", json={"notes": "entered on sweep confirmation"})
    assert resp.status_code == 200
    assert resp.json()["entry"]["notes"] == "entered on sweep confirmation"
    assert client.get("/api/journal").json()["entries"][0]["notes"] == "entered on sweep confirmation"

    missing = client.patch("/api/journal/999999/notes", json={"notes": "x"})
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_candle_cache_is_bounded(market_data):
    for i in range(80):
        await market_data.get_candles("EURUSD", "M15", 10 + i)
    assert len(market_data._candle_cache) <= market_data._MAX_CANDLE_CACHE_ENTRIES


@pytest.mark.asyncio
async def test_candle_count_clamped_to_config(market_data):
    candles = await market_data.get_candles("EURUSD", "M15", 10_000)
    assert len(candles) <= market_data.settings.candle_cache_size
