"""Basic indicator math over candle dicts (pure functions, no dependencies)."""

from __future__ import annotations


def ema(values: list[float], period: int) -> list[float]:
    if not values or period <= 0:
        return []
    k = 2 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def atr(candles: list[dict], period: int = 14) -> list[float]:
    if len(candles) < 2:
        return [0.0] * len(candles)
    trs = [candles[0]["high"] - candles[0]["low"]]
    for prev, cur in zip(candles, candles[1:]):
        trs.append(max(
            cur["high"] - cur["low"],
            abs(cur["high"] - prev["close"]),
            abs(cur["low"] - prev["close"]),
        ))
    out = [trs[0]]
    for tr in trs[1:]:
        out.append((out[-1] * (period - 1) + tr) / period)
    return out


def rate_of_change(values: list[float], period: int = 10) -> float:
    if len(values) <= period or values[-period - 1] == 0:
        return 0.0
    return (values[-1] - values[-period - 1]) / values[-period - 1] * 100
