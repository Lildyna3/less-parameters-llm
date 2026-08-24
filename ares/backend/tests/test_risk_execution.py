import pytest

from app.config import RiskSettings
from app.risk.engine import RiskEngine


def _ok_kwargs(**overrides):
    kwargs = dict(volume_lots=0.1, open_positions=0, total_exposure_lots=0.0,
                  account_balance=10000, account_equity=10000, spread_points=10)
    kwargs.update(overrides)
    return kwargs


def test_risk_allows_sane_order():
    engine = RiskEngine(RiskSettings())
    assert engine.check_order(**_ok_kwargs()).allowed


@pytest.mark.parametrize("kwargs,expected", [
    (_ok_kwargs(volume_lots=5.0), "max position size"),
    (_ok_kwargs(open_positions=5), "at limit"),
    (_ok_kwargs(total_exposure_lots=5.0), "exposure"),
    (_ok_kwargs(spread_points=100), "spread"),
    (_ok_kwargs(account_equity=8500), "drawdown"),
])
def test_risk_blocks(kwargs, expected):
    engine = RiskEngine(RiskSettings())
    decision = engine.check_order(**kwargs)
    assert not decision.allowed
    assert any(expected in r for r in decision.reasons)


def test_risk_daily_loss_and_emergency_stop():
    engine = RiskEngine(RiskSettings(cooldown_seconds_after_loss=0))
    engine.record_trade_closed(-600)  # beyond 500 daily loss limit
    assert not engine.check_order(**_ok_kwargs()).allowed

    engine2 = RiskEngine(RiskSettings())
    engine2.engage_emergency_stop("test")
    decision = engine2.check_order(**_ok_kwargs())
    assert not decision.allowed
    assert any("emergency" in r for r in decision.reasons)
    engine2.release_emergency_stop()
    assert engine2.check_order(**_ok_kwargs()).allowed


def test_risk_cooldown_after_loss():
    engine = RiskEngine(RiskSettings(cooldown_seconds_after_loss=60))
    engine.record_trade_closed(-10)
    decision = engine.check_order(**_ok_kwargs())
    assert not decision.allowed
    assert any("cooldown" in r for r in decision.reasons)


@pytest.mark.asyncio
async def test_paper_order_lifecycle(paper):
    result = await paper.submit_order("EURUSD", "buy", 0.1, sl=None, tp=None, strategy="test")
    assert result.success, result.message
    assert len(paper.positions) == 1
    pos_id = result.position["id"]

    await paper.mark_to_market()
    close = await paper.close_position(pos_id)
    assert close.success
    assert len(paper.positions) == 0
    assert len(paper.history) == 1
    snap = paper.account_snapshot()
    assert snap["mode"] == "PAPER"
    assert snap["trades_closed"] == 1


@pytest.mark.asyncio
async def test_paper_validates_sl_side(paper):
    tick = await paper.market_data.get_tick("EURUSD")
    bad = await paper.validate_order("EURUSD", "buy", 0.1, sl=tick["ask"] + 0.01, tp=None)
    assert not bad.success
    assert "SL must be below" in bad.message


@pytest.mark.asyncio
async def test_paper_refuses_without_data(paper):
    result = await paper.validate_order("NOSYMBOL", "buy", 0.1, None, None)
    assert not result.success
    assert "OFFLINE" in result.message


@pytest.mark.asyncio
async def test_paper_refuses_live_mode(market_data, risk):
    from app.config import ExecutionSettings
    from app.execution.paper import PaperTradingEngine

    engine = PaperTradingEngine(market_data, risk, ExecutionSettings(live_trading_enabled=True))
    result = await engine.validate_order("EURUSD", "buy", 0.1, None, None)
    assert not result.success
    assert "not available" in result.message


@pytest.mark.asyncio
async def test_paper_sl_hit_closes_position(paper):
    tick = await paper.market_data.get_tick("EURUSD")
    entry = tick["ask"]
    result = await paper.submit_order("EURUSD", "buy", 0.1, sl=entry - 0.0001, tp=None)
    assert result.success
    pos = list(paper.positions.values())[0]
    # Force a tick below the SL and mark to market.
    paper.market_data.latest_ticks["EURUSD"] = {
        "symbol": "EURUSD", "bid": pos.sl - 0.0005, "ask": pos.sl - 0.0003,
        "spread_points": 2, "source": "SIMULATED",
    }
    await paper.mark_to_market()
    assert len(paper.positions) == 0
    assert paper.history[-1].close_reason == "stop-loss hit"


@pytest.mark.asyncio
async def test_risk_blocks_paper_order(paper):
    blocked = await paper.submit_order("EURUSD", "buy", 3.0, None, None)  # > max 1.0 lots
    assert not blocked.success
    assert blocked.risk and not blocked.risk["allowed"]


@pytest.mark.asyncio
async def test_position_sizing(paper):
    lots = paper.position_size_for_risk("EURUSD", entry=1.1000, sl=1.0950, risk_amount=50)
    # 50 / (0.005 * 100000) = 0.1 lots
    assert lots == pytest.approx(0.1, abs=0.01)


@pytest.mark.asyncio
async def test_baskets_group_and_close(paper, baskets):
    basket = baskets.create("test-strategy", "EURUSD", "buy", max_loss=100)
    for _ in range(2):
        result = await paper.submit_order("EURUSD", "buy", 0.05, None, None, basket_id=basket.id)
        assert result.success
    view = baskets.basket_view(basket)
    assert view["open_trades"] == 2
    assert view["combined_exposure_lots"] == pytest.approx(0.1)

    found = baskets.find(f"#{basket.id}")
    assert found is basket
    result = await baskets.close_basket(basket.id)
    assert result["success"]
    assert len(paper.positions) == 0
    assert baskets.basket_view(basket)["status"] == "closed"


@pytest.mark.asyncio
async def test_emergency_close_all(paper):
    await paper.submit_order("EURUSD", "buy", 0.05, None, None)
    await paper.submit_order("GBPUSD", "sell", 0.05, None, None)
    closed = await paper.emergency_close_all()
    assert len(closed) == 2
    assert not paper.positions
