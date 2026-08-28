"""Trading-session awareness (Asian / London / New York / overlaps).

Uses the real system clock in UTC — nothing is hard-coded to a fixed date.
Session boundaries are the commonly used UTC approximations; DST nuances are
noted in the payload rather than silently ignored.
"""

from __future__ import annotations

from datetime import datetime, timezone

SESSIONS_UTC = {
    "Asian": (0, 9),      # Tokyo ~00:00–09:00 UTC
    "London": (7, 16),    # ~07:00–16:00 UTC
    "New York": (12, 21), # ~12:00–21:00 UTC
}


def current_sessions(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    hour = now.hour + now.minute / 60
    weekday = now.weekday()  # 0=Mon .. 6=Sun

    # FX market closes ~Friday 21:00 UTC, reopens ~Sunday 21:00 UTC.
    fx_open = not (
        (weekday == 4 and hour >= 21) or weekday == 5 or (weekday == 6 and hour < 21)
    )

    active = [
        name for name, (start, end) in SESSIONS_UTC.items()
        if fx_open and start <= hour < end
    ]
    overlap = None
    if "London" in active and "New York" in active:
        overlap = "London/New York overlap"
    elif "Asian" in active and "London" in active:
        overlap = "Asian/London overlap"

    return {
        "utc_time": now.isoformat(timespec="seconds"),
        "fx_market_open": fx_open,
        "active_sessions": active,
        "overlap": overlap,
        "note": "Session times are UTC approximations; exact boundaries shift with DST.",
    }
