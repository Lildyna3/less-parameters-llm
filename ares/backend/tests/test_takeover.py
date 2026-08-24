import time

import pytest

from app.execution.takeover import TakeoverState


def _proposed(symbol="EURUSD", direction="buy"):
    return [{"symbol": symbol, "direction": direction, "volume": 0.05,
             "sl": 1.0500, "tp": 1.2000}]


def test_request_requires_trades(takeover):
    result = takeover.request(symbol="EURUSD", direction="buy", reason="r",
                              confidence=4, proposed_trades=[])
    assert not result["success"]


def test_request_then_authorize_flow(takeover):
    result = takeover.request(symbol="EURUSD", direction="buy", reason="strong setup",
                              confidence=4, proposed_trades=_proposed())
    assert result["success"]
    session_id = result["session"]["id"]
    assert result["session"]["state"] == "REQUESTED"

    # Wrong id refused.
    assert not takeover.authorize("TK-bogus")["success"]

    auth = takeover.authorize(session_id)
    assert auth["success"]
    assert takeover.session.state == TakeoverState.ACTIVE
    assert takeover.session.basket_id


def test_authorization_expiry(takeover):
    result = takeover.request(symbol="EURUSD", direction="buy", reason="r",
                              confidence=4, proposed_trades=_proposed())
    session_id = result["session"]["id"]
    takeover.session.requested_at = time.monotonic() - takeover.settings.authorization_ttl_seconds - 1
    auth = takeover.authorize(session_id)
    assert not auth["success"]
    assert "expired" in auth["message"].lower()


def test_limits_are_capped(takeover):
    many = _proposed() * 10
    result = takeover.request(symbol="EURUSD", direction="buy", reason="r", confidence=5,
                              proposed_trades=many, max_loss=99999, duration_seconds=999999)
    session = result["session"]
    assert session["max_trades"] <= takeover.settings.max_trades
    assert session["max_loss"] <= takeover.settings.max_total_risk
    assert session["duration_seconds"] <= takeover.settings.max_duration_seconds


def test_no_duplicate_sessions(takeover):
    takeover.request(symbol="EURUSD", direction="buy", reason="r",
                     confidence=4, proposed_trades=_proposed())
    second = takeover.request(symbol="GBPUSD", direction="sell", reason="r",
                              confidence=4, proposed_trades=_proposed("GBPUSD", "sell"))
    assert not second["success"]


@pytest.mark.asyncio
async def test_tick_executes_once_and_deadline_stops(takeover, paper):
    result = takeover.request(symbol="EURUSD", direction="buy", reason="r",
                              confidence=4, proposed_trades=_proposed())
    takeover.authorize(result["session"]["id"])

    await takeover.tick()
    assert takeover.session.trades_executed == 1
    assert len(paper.positions) == 1

    # Second tick must not duplicate the order.
    await takeover.tick()
    assert len(paper.positions) == 1

    # Force the deadline; session must auto-stop and close its basket.
    takeover.session.authorized_at = time.monotonic() - takeover.session.duration_seconds - 1
    await takeover.tick()
    assert takeover.session is None
    assert len(paper.positions) == 0
    assert takeover.history and takeover.history[-1]["state"] == "STOPPED"


@pytest.mark.asyncio
async def test_stop_closes_basket(takeover, paper):
    result = takeover.request(symbol="EURUSD", direction="buy", reason="r",
                              confidence=4, proposed_trades=_proposed())
    takeover.authorize(result["session"]["id"])
    await takeover.tick()
    assert len(paper.positions) == 1
    stop = await takeover.stop(reason="user cancel")
    assert stop["success"]
    assert len(paper.positions) == 0
