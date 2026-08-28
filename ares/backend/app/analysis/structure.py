"""Market-structure detection: swings, trend, BOS/CHOCH, liquidity,
dealing range with premium/discount/equilibrium, support/resistance.

Everything here is evidence, not prediction. Each detector returns plain
dicts the engine and the UI consume; nothing is presented as guaranteed.
"""

from __future__ import annotations

from .indicators import atr, ema, rate_of_change


def find_swings(candles: list[dict], strength: int = 3) -> list[dict]:
    """Fractal pivots: a swing high/low is an extreme among `strength`
    neighbors on each side. Returned oldest-first."""
    swings: list[dict] = []
    n = len(candles)
    for i in range(strength, n - strength):
        window = candles[i - strength: i + strength + 1]
        high, low = candles[i]["high"], candles[i]["low"]
        if high == max(c["high"] for c in window):
            swings.append({"type": "high", "index": i, "price": high, "time": candles[i]["time"]})
        if low == min(c["low"] for c in window):
            swings.append({"type": "low", "index": i, "price": low, "time": candles[i]["time"]})
    return swings


def classify_trend(candles: list[dict], swings: list[dict]) -> dict:
    """Trend from swing sequence + EMA slope. Returns direction and score in
    [-1, 1] (negative = bearish)."""
    closes = [c["close"] for c in candles]
    score = 0.0
    evidence: list[str] = []

    highs = [s for s in swings if s["type"] == "high"][-3:]
    lows = [s for s in swings if s["type"] == "low"][-3:]
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1]["price"] > highs[-2]["price"]
        hl = lows[-1]["price"] > lows[-2]["price"]
        lh = highs[-1]["price"] < highs[-2]["price"]
        ll = lows[-1]["price"] < lows[-2]["price"]
        if hh and hl:
            score += 0.5
            evidence.append("higher highs and higher lows")
        elif lh and ll:
            score -= 0.5
            evidence.append("lower highs and lower lows")
        else:
            evidence.append("mixed swing sequence")

    if len(closes) >= 50:
        e20, e50 = ema(closes, 20)[-1], ema(closes, 50)[-1]
        if e20 > e50 and closes[-1] > e20:
            score += 0.3
            evidence.append("price above rising EMA20>EMA50")
        elif e20 < e50 and closes[-1] < e20:
            score -= 0.3
            evidence.append("price below falling EMA20<EMA50")

    roc = rate_of_change(closes, 10)
    if abs(roc) > 0.05:
        score += 0.2 if roc > 0 else -0.2
        evidence.append(f"10-bar momentum {roc:+.2f}%")

    score = max(-1.0, min(1.0, score))
    direction = "bullish" if score > 0.25 else "bearish" if score < -0.25 else "ranging"
    return {"direction": direction, "score": round(score, 2), "evidence": evidence}


def detect_structure_events(candles: list[dict], swings: list[dict]) -> dict:
    """Break of structure (BOS) / change of character (CHOCH) from the most
    recent close vs the last confirmed swing levels."""
    events: list[dict] = []
    highs = [s for s in swings if s["type"] == "high"]
    lows = [s for s in swings if s["type"] == "low"]
    if not candles or not highs or not lows:
        return {"events": events, "last_event": None}

    close = candles[-1]["close"]
    last_high, last_low = highs[-1], lows[-1]

    trend = classify_trend(candles[:-1], swings)["direction"]
    if close > last_high["price"]:
        kind = "BOS" if trend == "bullish" else "CHOCH"
        events.append({
            "kind": kind, "direction": "bullish", "level": last_high["price"],
            "time": candles[-1]["time"],
            "note": f"Close above swing high {last_high['price']}",
        })
    if close < last_low["price"]:
        kind = "BOS" if trend == "bearish" else "CHOCH"
        events.append({
            "kind": kind, "direction": "bearish", "level": last_low["price"],
            "time": candles[-1]["time"],
            "note": f"Close below swing low {last_low['price']}",
        })
    return {"events": events, "last_event": events[-1] if events else None}


def detect_liquidity(candles: list[dict], swings: list[dict], tolerance_atr: float = 0.25) -> dict:
    """Equal highs/lows (resting liquidity) and recent sweeps (wick beyond a
    swing level followed by close back inside)."""
    if len(candles) < 20:
        return {"pools": [], "sweeps": []}
    current_atr = atr(candles)[-1] or 1e-9
    tol = current_atr * tolerance_atr

    pools: list[dict] = []
    highs = [s for s in swings if s["type"] == "high"][-8:]
    lows = [s for s in swings if s["type"] == "low"][-8:]
    for group, side in ((highs, "buy-side"), (lows, "sell-side")):
        for a, b in zip(group, group[1:]):
            if abs(a["price"] - b["price"]) <= tol:
                pools.append({
                    "side": side,
                    "level": round((a["price"] + b["price"]) / 2, 6),
                    "note": f"equal {'highs' if side == 'buy-side' else 'lows'}",
                })

    sweeps: list[dict] = []
    recent = candles[-10:]
    for swing in highs:
        for c in recent:
            if c["high"] > swing["price"] and c["close"] < swing["price"]:
                sweeps.append({"side": "buy-side", "level": swing["price"], "time": c["time"],
                               "note": "wick above swing high, close back below (sweep)"})
                break
    for swing in lows:
        for c in recent:
            if c["low"] < swing["price"] and c["close"] > swing["price"]:
                sweeps.append({"side": "sell-side", "level": swing["price"], "time": c["time"],
                               "note": "wick below swing low, close back above (sweep)"})
                break
    return {"pools": pools[-6:], "sweeps": sweeps[-4:]}


def dealing_range(candles: list[dict], swings: list[dict]) -> dict | None:
    """Range between the last significant swing low and high, with
    premium/discount/equilibrium zoning of the current price."""
    highs = [s for s in swings if s["type"] == "high"]
    lows = [s for s in swings if s["type"] == "low"]
    if not highs or not lows or not candles:
        return None
    top = max(s["price"] for s in highs[-4:])
    bottom = min(s["price"] for s in lows[-4:])
    if top <= bottom:
        return None
    close = candles[-1]["close"]
    position = (close - bottom) / (top - bottom)
    zone = "premium" if position > 0.62 else "discount" if position < 0.38 else "equilibrium"
    return {
        "high": top, "low": bottom,
        "equilibrium": round((top + bottom) / 2, 6),
        "position": round(position, 3),
        "zone": zone,
    }


def support_resistance(swings: list[dict], current_price: float, max_levels: int = 6) -> list[dict]:
    """Nearest swing-based levels around the current price."""
    levels = []
    for s in swings[-30:]:
        levels.append({
            "price": s["price"],
            "kind": "resistance" if s["price"] > current_price else "support",
            "origin": f"swing {s['type']}",
        })
    levels.sort(key=lambda l: abs(l["price"] - current_price))
    seen: list[dict] = []
    for lvl in levels:
        if all(abs(lvl["price"] - s["price"]) / max(current_price, 1e-9) > 0.0005 for s in seen):
            seen.append(lvl)
        if len(seen) >= max_levels:
            break
    return sorted(seen, key=lambda l: l["price"], reverse=True)


def volatility_state(candles: list[dict]) -> dict:
    values = atr(candles)
    if len(values) < 30:
        return {"state": "unknown", "atr": values[-1] if values else 0.0, "ratio": None}
    current = values[-1]
    baseline = sum(values[-30:-5]) / 25 or 1e-9
    ratio = current / baseline
    state = "elevated" if ratio > 1.3 else "compressed" if ratio < 0.75 else "normal"
    return {"state": state, "atr": round(current, 6), "ratio": round(ratio, 2)}
