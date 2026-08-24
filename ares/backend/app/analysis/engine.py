"""Multi-timeframe analysis engine.

Produces the structured AI-output schema from spec §44 using measurable
evidence only. The optional LLM layer (ai/) may narrate this structure, but
never invents bias, confidence, or levels.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..market_data.service import MarketDataService
from .confidence import LABELS, score_confidence
from .structure import (
    classify_trend,
    dealing_range,
    detect_liquidity,
    detect_structure_events,
    find_swings,
    support_resistance,
    volatility_state,
)

HTF, MTF, LTF = "H4", "H1", "M15"


class AnalysisEngine:
    def __init__(self, market_data: MarketDataService, max_spread_points: float = 40.0) -> None:
        self.market_data = market_data
        self.max_spread_points = max_spread_points
        self.analyses_performed = 0

    async def analyze(self, symbol: str, news_risk: bool = False) -> dict | None:
        """Full multi-timeframe analysis. Returns None when market data is
        unavailable (never fabricates)."""
        frames: dict[str, list[dict]] = {}
        for tf in (HTF, MTF, LTF):
            candles = await self.market_data.get_candles(symbol, tf, 300)
            if len(candles) < 60:
                return None
            frames[tf] = candles

        tick = await self.market_data.get_tick(symbol)
        price = (tick["bid"] + tick["ask"]) / 2 if tick else frames[LTF][-1]["close"]
        spread_ok = None
        if tick and tick.get("spread_points") is not None:
            spread_ok = tick["spread_points"] <= self.max_spread_points

        per_tf: dict[str, dict] = {}
        for tf, candles in frames.items():
            swings = find_swings(candles)
            per_tf[tf] = {
                "trend": classify_trend(candles, swings),
                "structure": detect_structure_events(candles, swings),
                "liquidity": detect_liquidity(candles, swings),
                "dealing_range": dealing_range(candles, swings),
                "volatility": volatility_state(candles),
                "swings": swings,
            }

        ltf = per_tf[LTF]
        confidence = score_confidence(
            htf_trend=per_tf[HTF]["trend"],
            mtf_trend=per_tf[MTF]["trend"],
            ltf_trend=ltf["trend"],
            structure_event=per_tf[MTF]["structure"]["last_event"] or ltf["structure"]["last_event"],
            liquidity=ltf["liquidity"],
            dealing=per_tf[MTF]["dealing_range"],
            volatility=ltf["volatility"],
            spread_ok=spread_ok,
            news_risk=news_risk,
        )

        directions = {tf: per_tf[tf]["trend"]["direction"] for tf in (HTF, MTF, LTF)}
        unique = set(directions.values())
        if unique == {"bullish"}:
            alignment = "aligned bullish"
        elif unique == {"bearish"}:
            alignment = "aligned bearish"
        elif unique == {"ranging"}:
            alignment = "ranging"
        elif len(unique) == 1:
            alignment = "unclear"
        else:
            alignment = "mixed"

        key_levels = support_resistance(
            per_tf[MTF]["swings"] + per_tf[HTF]["swings"][-6:], price
        )

        market_state = (
            "trending" if alignment in ("aligned bullish", "aligned bearish")
            else "ranging" if alignment == "ranging" else "transitional"
        )

        scenarios, invalidations = self._scenarios(confidence.direction, per_tf, price)
        risk_factors = self._risks(ltf["volatility"], spread_ok, news_risk, tick)

        self.analyses_performed += 1
        return {
            "symbol": symbol,
            "bias": confidence.direction,
            "confidence": confidence.score,
            "confidence_label": LABELS[confidence.score],
            "confidence_factors": [f.__dict__ for f in confidence.factors],
            "market_state": market_state,
            "timeframe_alignment": alignment,
            "timeframes": {
                tf: {
                    "trend": data["trend"],
                    "last_structure_event": data["structure"]["last_event"],
                    "dealing_range": data["dealing_range"],
                    "volatility": data["volatility"],
                }
                for tf, data in per_tf.items()
            },
            "structure": self._structure_summary(per_tf),
            "liquidity": ltf["liquidity"],
            "key_levels": key_levels,
            "scenarios": scenarios,
            "invalidations": invalidations,
            "risk_factors": risk_factors,
            "price": price,
            "data_source": self.market_data.source_label,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def _structure_summary(self, per_tf: dict) -> str:
        parts = []
        for tf in (HTF, MTF, LTF):
            trend = per_tf[tf]["trend"]
            event = per_tf[tf]["structure"]["last_event"]
            text = f"{tf} {trend['direction']}"
            if event:
                text += f" with recent {event['kind']} {event['direction']}"
            parts.append(text)
        return "; ".join(parts)

    def _scenarios(self, direction: str, per_tf: dict, price: float):
        scenarios, invalidations = [], []
        mtf = per_tf[MTF]
        lows = [s["price"] for s in mtf["swings"] if s["type"] == "low"]
        highs = [s["price"] for s in mtf["swings"] if s["type"] == "high"]
        last_low = max((p for p in lows if p < price), default=None)
        last_high = min((p for p in highs if p > price), default=None)

        if direction == "bullish":
            scenarios.append({
                "name": "continuation long",
                "description": "Hold above the last H1 swing low and look for LTF confirmation before considering longs.",
            })
            if last_high:
                scenarios.append({"name": "liquidity run", "description": f"Buy-side liquidity rests above {last_high}; price may draw to it."})
            if last_low:
                invalidations.append(f"H1 close below {last_low} invalidates the bullish read")
        elif direction == "bearish":
            scenarios.append({
                "name": "continuation short",
                "description": "Hold below the last H1 swing high and look for LTF confirmation before considering shorts.",
            })
            if last_low:
                scenarios.append({"name": "liquidity run", "description": f"Sell-side liquidity rests below {last_low}; price may draw to it."})
            if last_high:
                invalidations.append(f"H1 close above {last_high} invalidates the bearish read")
        else:
            scenarios.append({
                "name": "range rotation",
                "description": "No directional edge; expect rotation inside the dealing range until structure breaks.",
            })
            if last_low and last_high:
                invalidations.append(f"a decisive H1 close outside {last_low}–{last_high} ends the range read")
        return scenarios, invalidations

    def _risks(self, vol: dict, spread_ok: bool | None, news_risk: bool, tick: dict | None) -> list[str]:
        risks = []
        if vol["state"] == "elevated":
            risks.append("volatility is elevated vs its recent baseline")
        if spread_ok is False:
            risks.append("spread is currently above the configured limit")
        if news_risk:
            risks.append("high-impact news event scheduled nearby")
        if tick is None:
            risks.append("no live tick available — analysis based on last candles only")
        if tick and tick.get("source") == "SIMULATED":
            risks.append("data source is SIMULATED (demo/testing feed), not live market prices")
        return risks
