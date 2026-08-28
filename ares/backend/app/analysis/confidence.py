"""Evidence-based confidence scoring (1–5).

The score is computed from measurable factors — never invented by a language
model. Each factor contributes points with a stated reason so the UI and the
Command Center can show exactly WHY a score exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConfidenceFactor:
    name: str
    points: float          # contribution in [-1, +1] per factor
    reason: str


@dataclass
class ConfidenceResult:
    score: int             # 1..5
    direction: str         # bullish / bearish / neutral
    factors: list[ConfidenceFactor] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "direction": self.direction,
            "factors": [f.__dict__ for f in self.factors],
        }


LABELS = {
    1: "Very weak evidence",
    2: "Weak setup",
    3: "Interesting but uncertain",
    4: "Strong confluence",
    5: "Very strong confluence",
}


def score_confidence(
    *,
    htf_trend: dict,
    mtf_trend: dict,
    ltf_trend: dict,
    structure_event: dict | None,
    liquidity: dict,
    dealing: dict | None,
    volatility: dict,
    spread_ok: bool | None = None,
    news_risk: bool = False,
) -> ConfidenceResult:
    factors: list[ConfidenceFactor] = []

    # Directional consensus across timeframes.
    scores = [htf_trend["score"], mtf_trend["score"], ltf_trend["score"]]
    consensus = sum(scores) / 3
    direction = "bullish" if consensus > 0.15 else "bearish" if consensus < -0.15 else "neutral"
    sign = 1 if direction == "bullish" else -1 if direction == "bearish" else 0

    aligned = sum(1 for s in scores if s * sign > 0.2) if sign else 0
    factors.append(ConfidenceFactor(
        "timeframe_alignment",
        {3: 1.0, 2: 0.5, 1: 0.1, 0: -0.5}[aligned],
        f"{aligned}/3 timeframes aligned {direction}" if sign else "no directional consensus",
    ))

    factors.append(ConfidenceFactor(
        "htf_trend", htf_trend["score"] * sign if sign else -0.2,
        f"higher timeframe is {htf_trend['direction']} (score {htf_trend['score']})",
    ))

    if structure_event:
        agrees = structure_event["direction"] == direction
        factors.append(ConfidenceFactor(
            "structure",
            0.6 if agrees else -0.6,
            f"recent {structure_event['kind']} {structure_event['direction']} "
            f"{'supports' if agrees else 'contradicts'} the {direction} read",
        ))
    else:
        factors.append(ConfidenceFactor("structure", 0.0, "no recent BOS/CHOCH"))

    sweeps = liquidity.get("sweeps", [])
    supporting = [
        s for s in sweeps
        if (s["side"] == "sell-side" and direction == "bullish")
        or (s["side"] == "buy-side" and direction == "bearish")
    ]
    if supporting:
        factors.append(ConfidenceFactor(
            "liquidity", 0.6,
            f"{supporting[0]['side']} liquidity swept — often precedes a move {direction}",
        ))
    elif sweeps:
        factors.append(ConfidenceFactor("liquidity", -0.2, "recent sweep against the read"))
    else:
        factors.append(ConfidenceFactor("liquidity", 0.0, "no recent liquidity sweep"))

    if dealing:
        good_zone = (direction == "bullish" and dealing["zone"] == "discount") or \
                    (direction == "bearish" and dealing["zone"] == "premium")
        factors.append(ConfidenceFactor(
            "premium_discount",
            0.4 if good_zone else -0.3 if dealing["zone"] != "equilibrium" else 0.0,
            f"price in {dealing['zone']} of the dealing range (pos {dealing['position']})",
        ))

    if volatility["state"] == "elevated":
        factors.append(ConfidenceFactor("volatility", -0.3, "volatility elevated — execution risk up"))
    elif volatility["state"] == "compressed":
        factors.append(ConfidenceFactor("volatility", 0.1, "volatility compressed — expansion possible"))
    else:
        factors.append(ConfidenceFactor("volatility", 0.1, "volatility normal"))

    if spread_ok is False:
        factors.append(ConfidenceFactor("spread", -0.5, "spread above configured limit"))
    elif spread_ok:
        factors.append(ConfidenceFactor("spread", 0.1, "spread within limits"))

    if news_risk:
        factors.append(ConfidenceFactor("news_risk", -0.6, "high-impact news event nearby"))

    total = sum(f.points for f in factors)
    # Map total (~[-3, +3.5]) to 1..5.
    if sign == 0:
        score = 1 if total < 0 else 2
    elif total >= 2.4:
        score = 5
    elif total >= 1.6:
        score = 4
    elif total >= 0.8:
        score = 3
    elif total >= 0.2:
        score = 2
    else:
        score = 1

    return ConfidenceResult(score=score, direction=direction, factors=factors)
