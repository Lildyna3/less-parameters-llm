import pytest

from app.analysis.confidence import score_confidence
from app.analysis.engine import AnalysisEngine
from app.analysis.indicators import atr, ema, rate_of_change
from app.analysis.structure import (
    classify_trend,
    dealing_range,
    detect_liquidity,
    detect_structure_events,
    find_swings,
    volatility_state,
)


def make_trend_candles(n=120, start=100.0, step=0.5, wiggle=0.2):
    """Zigzag trend: 8 bars with the trend, 4 bars against at half size.
    Produces real fractal swing highs/lows (HH/HL when step>0)."""
    candles = []
    price = start
    for i in range(n):
        direction = 1 if (i % 12) < 8 else -0.5
        open_p = price
        close_p = price + step * direction
        high = max(open_p, close_p) + wiggle
        low = min(open_p, close_p) - wiggle
        candles.append({"time": 1_700_000_000 + i * 900, "open": open_p,
                        "high": high, "low": low, "close": close_p, "volume": 100})
        price = close_p
    return candles


def test_indicators_basic():
    values = [1, 2, 3, 4, 5]
    assert len(ema(values, 3)) == 5
    assert ema(values, 3)[-1] > ema(values, 3)[0]
    candles = make_trend_candles(30)
    assert len(atr(candles)) == 30
    assert atr(candles)[-1] > 0
    assert rate_of_change([100] * 5 + [110], 5) == pytest.approx(10.0)


def test_swings_and_trend_up():
    candles = make_trend_candles()
    swings = find_swings(candles)
    assert swings, "should detect fractal swings"
    trend = classify_trend(candles, swings)
    assert trend["direction"] == "bullish"
    assert trend["score"] > 0.25
    assert trend["evidence"]


def test_trend_down():
    candles = make_trend_candles(step=-0.5)
    swings = find_swings(candles)
    trend = classify_trend(candles, swings)
    assert trend["direction"] == "bearish"


def test_structure_events_bos():
    candles = make_trend_candles()
    # force a strong close above all recent highs
    last = candles[-1]
    last["close"] = last["high"] = max(c["high"] for c in candles) + 5
    swings = find_swings(candles)
    events = detect_structure_events(candles, swings)
    assert events["last_event"] is not None
    assert events["last_event"]["direction"] == "bullish"


def test_liquidity_sweep_detected():
    candles = make_trend_candles(n=80, step=0.0, wiggle=0.3)
    # equal highs then a sweep: wick above, close back below
    for c in candles[-30:-5]:
        c["high"] = 101.0
    sweep = candles[-2]
    sweep["high"] = 101.8
    sweep["close"] = 100.4
    swings = find_swings(candles)
    liq = detect_liquidity(candles, swings)
    assert isinstance(liq["pools"], list)
    assert any(s["side"] == "buy-side" for s in liq["sweeps"])


def test_dealing_range_zones():
    candles = make_trend_candles(n=100, step=0.0, wiggle=1.0)
    swings = find_swings(candles)
    dr = dealing_range(candles, swings)
    assert dr is not None
    assert dr["low"] < dr["equilibrium"] < dr["high"]
    assert dr["zone"] in ("premium", "discount", "equilibrium")


def test_volatility_state():
    candles = make_trend_candles(n=60)
    vol = volatility_state(candles)
    assert vol["state"] in ("normal", "elevated", "compressed")
    assert vol["atr"] > 0


def test_confidence_alignment_beats_conflict():
    bull = {"direction": "bullish", "score": 0.8, "evidence": []}
    bear = {"direction": "bearish", "score": -0.8, "evidence": []}
    flat = {"direction": "ranging", "score": 0.0, "evidence": []}
    vol = {"state": "normal", "atr": 1.0, "ratio": 1.0}
    liq_support = {"pools": [], "sweeps": [{"side": "sell-side", "level": 1.0, "note": "x"}]}
    dealing = {"zone": "discount", "position": 0.2, "high": 2, "low": 1, "equilibrium": 1.5}

    aligned = score_confidence(
        htf_trend=bull, mtf_trend=bull, ltf_trend=bull,
        structure_event={"kind": "BOS", "direction": "bullish"},
        liquidity=liq_support, dealing=dealing, volatility=vol, spread_ok=True,
    )
    conflicted = score_confidence(
        htf_trend=bull, mtf_trend=bear, ltf_trend=flat,
        structure_event=None, liquidity={"pools": [], "sweeps": []},
        dealing=None, volatility=vol,
    )
    assert 1 <= conflicted.score < aligned.score <= 5
    assert aligned.score >= 4
    assert aligned.direction == "bullish"
    assert all(f.reason for f in aligned.factors)


def test_confidence_news_risk_reduces_score():
    bull = {"direction": "bullish", "score": 0.8, "evidence": []}
    vol = {"state": "normal", "atr": 1.0, "ratio": 1.0}
    base = score_confidence(htf_trend=bull, mtf_trend=bull, ltf_trend=bull,
                            structure_event=None, liquidity={"pools": [], "sweeps": []},
                            dealing=None, volatility=vol)
    with_news = score_confidence(htf_trend=bull, mtf_trend=bull, ltf_trend=bull,
                                 structure_event=None, liquidity={"pools": [], "sweeps": []},
                                 dealing=None, volatility=vol, news_risk=True)
    assert with_news.score <= base.score


@pytest.mark.asyncio
async def test_engine_full_analysis(market_data):
    engine = AnalysisEngine(market_data)
    analysis = await engine.analyze("EURUSD")
    assert analysis is not None
    assert analysis["symbol"] == "EURUSD"
    assert analysis["bias"] in ("bullish", "bearish", "neutral")
    assert 1 <= analysis["confidence"] <= 5
    assert analysis["data_source"] == "SIMULATED"
    assert analysis["timeframe_alignment"] in (
        "aligned bullish", "aligned bearish", "mixed", "ranging", "unclear")
    assert analysis["confidence_factors"]
    assert "H4" in analysis["timeframes"]


@pytest.mark.asyncio
async def test_engine_refuses_without_data(risk):
    from app.config import MarketDataSettings
    from app.market_data.providers import MT5Provider
    from app.market_data.service import MarketDataService
    from app.mt5.adapter import MT5Adapter
    from app.config import MT5Settings

    adapter = MT5Adapter(MT5Settings())  # not connected
    md = MarketDataService(MT5Provider(adapter), MarketDataSettings())
    engine = AnalysisEngine(md)
    assert await engine.analyze("EURUSD") is None
