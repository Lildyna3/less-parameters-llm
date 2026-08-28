"""ARES coaching: pattern detection over the recorded trade journal.

Coaching statements are derived only from recorded behavior — counts and
measurable ratios — never from invented psychology. With too few trades the
coach says so instead of guessing.
"""

from __future__ import annotations

MIN_TRADES = 10


def coach_from_journal(entries: list[dict]) -> dict:
    n = len(entries)
    if n < MIN_TRADES:
        return {
            "trades_analyzed": n,
            "observations": [],
            "message": f"Not enough recorded trades to coach yet ({n}/{MIN_TRADES}). "
                       "Keep trading the demo account and I'll look for patterns.",
        }

    observations: list[dict] = []
    recent = entries[:30]  # entries come newest-first

    losses = [e for e in recent if e["pl"] < 0]
    wins = [e for e in recent if e["pl"] > 0]

    # Overtrading: many trades per distinct day.
    days = {e["closed_at"][:10] for e in recent}
    per_day = len(recent) / max(len(days), 1)
    if per_day > 6:
        observations.append({
            "pattern": "overtrading",
            "evidence": f"{len(recent)} trades across {len(days)} day(s) — {per_day:.1f}/day",
            "advice": "Trade count per day is high. Consider capping daily trades and only acting on 4/5+ evidence.",
        })

    # Poor risk/reward: average loss magnitude vs average win.
    if wins and losses:
        avg_win = sum(e["pl"] for e in wins) / len(wins)
        avg_loss = abs(sum(e["pl"] for e in losses) / len(losses))
        if avg_loss > 1.5 * avg_win:
            observations.append({
                "pattern": "poor risk/reward",
                "evidence": f"average loss {avg_loss:.2f} vs average win {avg_win:.2f}",
                "advice": "Losses run bigger than wins. Tighten stops or take profits further from entry.",
            })

    # No stop-loss habit.
    no_sl = [e for e in recent if e["sl"] is None]
    if len(no_sl) > len(recent) * 0.3:
        observations.append({
            "pattern": "missing stop-losses",
            "evidence": f"{len(no_sl)}/{len(recent)} recent trades had no SL",
            "advice": "A third or more of your trades run without a stop. Define invalidation before entering.",
        })

    # Low-confidence entries losing.
    low_conf = [e for e in recent if (e.get("confidence") or 0) <= 2]
    low_conf_losses = [e for e in low_conf if e["pl"] < 0]
    if len(low_conf) >= 5 and len(low_conf_losses) / len(low_conf) > 0.6:
        observations.append({
            "pattern": "trading weak evidence",
            "evidence": f"{len(low_conf_losses)}/{len(low_conf)} low-confidence (≤2/5) trades lost",
            "advice": "Entries taken on weak evidence are mostly losing. Wait for 3/5+ setups.",
        })

    # Repeated stop-outs (entering early / against structure proxy).
    stop_outs = [e for e in recent if e["close_reason"] == "stop-loss hit"]
    if len(stop_outs) >= 5 and len(stop_outs) / len(recent) > 0.5:
        observations.append({
            "pattern": "entering before confirmation",
            "evidence": f"{len(stop_outs)}/{len(recent)} recent trades ended at the stop-loss",
            "advice": f"Your last {len(recent)} trades show a pattern of entering before confirmation. "
                      "Consider waiting for structure confirmation.",
        })

    message = ("No concerning behavioral patterns detected in your recorded trades."
               if not observations else
               f"Found {len(observations)} pattern(s) in your last {len(recent)} recorded trades.")
    return {"trades_analyzed": len(recent), "observations": observations, "message": message}
