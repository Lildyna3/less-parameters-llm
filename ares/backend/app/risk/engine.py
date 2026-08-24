"""Risk management engine — first-class, blocking, and auditable.

Every order (paper or, in the future, live) passes check_order(); a rejected
check is a hard block. The engine also owns the emergency stop and the
post-loss cooldown. All decisions are returned with explicit reasons and
logged.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import RiskSettings
from ..logging_setup import get_logger

log = get_logger("risk")


@dataclass
class RiskDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"allowed": self.allowed, "reasons": self.reasons}


class RiskEngine:
    def __init__(self, settings: RiskSettings) -> None:
        self.settings = settings
        self.emergency_stop = settings.emergency_stop_engaged
        self._daily_pl = 0.0
        self._daily_key = self._today()
        self._session_trades = 0
        self._cooldown_until = 0.0
        self.blocks_issued = 0

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _roll_day(self) -> None:
        today = self._today()
        if today != self._daily_key:
            self._daily_key = today
            self._daily_pl = 0.0
            self._session_trades = 0

    # -- event hooks -----------------------------------------------------------

    def record_trade_opened(self) -> None:
        self._roll_day()
        self._session_trades += 1

    def record_trade_closed(self, pl: float) -> None:
        self._roll_day()
        self._daily_pl += pl
        if pl < 0 and self.settings.cooldown_seconds_after_loss > 0:
            self._cooldown_until = time.monotonic() + self.settings.cooldown_seconds_after_loss

    def engage_emergency_stop(self, reason: str) -> None:
        self.emergency_stop = True
        log.warning("EMERGENCY STOP engaged: %s", reason)

    def release_emergency_stop(self) -> None:
        self.emergency_stop = False
        log.info("Emergency stop released")

    # -- checks ------------------------------------------------------------------

    def check_order(
        self,
        *,
        volume_lots: float,
        open_positions: int,
        total_exposure_lots: float,
        account_balance: float,
        account_equity: float,
        spread_points: float | None,
        estimated_risk: float | None = None,
    ) -> RiskDecision:
        self._roll_day()
        s = self.settings
        reasons: list[str] = []

        if self.emergency_stop:
            reasons.append("emergency stop is engaged")
        if time.monotonic() < self._cooldown_until:
            remaining = int(self._cooldown_until - time.monotonic())
            reasons.append(f"post-loss cooldown active ({remaining}s remaining)")
        if volume_lots <= 0:
            reasons.append("volume must be positive")
        if volume_lots > s.max_position_size_lots:
            reasons.append(f"volume {volume_lots} exceeds max position size {s.max_position_size_lots} lots")
        if open_positions >= s.max_open_positions:
            reasons.append(f"open positions ({open_positions}) at limit ({s.max_open_positions})")
        if total_exposure_lots + volume_lots > s.max_exposure_lots:
            reasons.append(f"total exposure would exceed {s.max_exposure_lots} lots")
        if self._session_trades >= s.max_trades_per_session:
            reasons.append(f"session trade limit reached ({s.max_trades_per_session})")
        if self._daily_pl <= -s.max_daily_loss:
            reasons.append(f"daily loss limit reached ({self._daily_pl:.2f} vs -{s.max_daily_loss})")
        if account_balance > 0:
            drawdown_pct = (account_balance - account_equity) / account_balance * 100
            if drawdown_pct >= s.max_drawdown_percent:
                reasons.append(f"drawdown {drawdown_pct:.1f}% at/above limit {s.max_drawdown_percent}%")
        if spread_points is not None and spread_points > s.max_spread_points:
            reasons.append(f"spread {spread_points} points above limit {s.max_spread_points}")
        if estimated_risk is not None and estimated_risk > s.max_daily_loss:
            reasons.append("estimated single-trade risk exceeds the daily loss limit")

        decision = RiskDecision(allowed=not reasons, reasons=reasons)
        if not decision.allowed:
            self.blocks_issued += 1
            log.info("risk block: %s", "; ".join(reasons))
        return decision

    def snapshot(self) -> dict:
        self._roll_day()
        return {
            "emergency_stop": self.emergency_stop,
            "daily_pl": round(self._daily_pl, 2),
            "session_trades": self._session_trades,
            "cooldown_active": time.monotonic() < self._cooldown_until,
            "blocks_issued": self.blocks_issued,
            "limits": self.settings.model_dump(),
        }
