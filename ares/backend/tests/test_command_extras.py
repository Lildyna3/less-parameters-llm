"""Tests for the 'what changed' intent, remember() history, and daily
change-reference loading in the market-data service."""

import pytest

from app.ai.command import CommandCenter
from app.analysis.engine import AnalysisEngine
from app.config import NewsSettings, TakeoverSettings
from app.execution.baskets import BasketManager
from app.execution.takeover import TakeoverManager
from app.news.calendar import EconomicCalendar
from app.scanner.scanner import MarketScanner


@pytest.fixture
def command(market_data, paper, risk) -> CommandCenter:
    engine = AnalysisEngine(market_data)
    baskets = BasketManager(paper)
    takeover = TakeoverManager(paper, baskets, TakeoverSettings())
    return CommandCenter(
        market_data, engine, MarketScanner(engine), paper, baskets,
        takeover, risk, EconomicCalendar(NewsSettings()),
    )


@pytest.mark.asyncio
async def test_what_changed_requires_prior_analysis(command):
    resp = await command.handle("What changed?")
    assert "run an analysis first" in resp["reply"].lower()


@pytest.mark.asyncio
async def test_what_changed_diffs_against_previous(command):
    first = await command.handle("Analyze EURUSD")
    assert first.get("analysis")

    resp = await command.handle("What changed?")
    assert resp["reply"].startswith("EURUSD since your last analysis:")
    assert resp.get("analysis") is not None
    # Price line is always included when a baseline price exists.
    assert "price" in resp["reply"]
    # History rotated: the pre-diff analysis became the previous one.
    assert "EURUSD" in command.previous_analysis


@pytest.mark.asyncio
async def test_remember_keeps_one_level_of_history(command):
    a1 = {"symbol": "GBPUSD", "bias": "bullish"}
    a2 = {"symbol": "GBPUSD", "bias": "bearish"}
    command.remember(a1)
    assert "GBPUSD" not in command.previous_analysis
    command.remember(a2)
    assert command.previous_analysis["GBPUSD"] is a1
    assert command.last_analysis["GBPUSD"] is a2


@pytest.mark.asyncio
async def test_daily_references_populate_change_stats(market_data):
    await market_data._ensure_daily_references()
    # Limited to a few per call; run until the watched list is covered.
    for _ in range(len(market_data.watched_symbols)):
        market_data._daily_refs_checked_at = -3600.0
        await market_data._ensure_daily_references()
    assert market_data._prev_day_close, "previous-day closes should be loaded"

    symbol = next(iter(market_data._prev_day_close))
    tick = await market_data.provider.get_tick(symbol)
    stats = market_data._change_stats(symbol, tick)
    assert stats["change"] is not None
    assert stats["change_percent"] is not None
