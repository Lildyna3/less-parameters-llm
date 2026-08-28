"""Foundation tests: config, secret redaction, MT5 detection honesty,
sessions, calendar, coaching, database."""

import json
import logging

import pytest

from app.ai.coach import coach_from_journal
from app.config import AresConfig, MT5Settings
from app.database import Database
from app.logging_setup import JsonFormatter, RedactionFilter, register_secret
from app.market_data.sessions import current_sessions
from app.mt5.adapter import MT5Adapter, mask_login
from app.mt5.detect import detect_mt5
from app.news.calendar import EconomicCalendar
from app.config import NewsSettings


def test_config_loads_with_defaults(monkeypatch):
    monkeypatch.delenv("MT5_LOGIN", raising=False)
    config = AresConfig()
    assert config.execution.live_trading_enabled is False
    assert config.market_data.mode == "mt5"
    assert not config.mt5.credentials_configured
    assert "EURUSD" in config.market_data.default_symbols


def test_config_reads_mt5_env(monkeypatch):
    monkeypatch.setenv("MT5_LOGIN", "12345678")
    monkeypatch.setenv("MT5_PASSWORD", "hunter2secret")
    monkeypatch.setenv("MT5_SERVER", "Broker-Demo")
    config = AresConfig()
    assert config.mt5.credentials_configured
    assert config.mt5.login == 12345678


def test_log_redaction():
    register_secret("hunter2secret")
    record = logging.LogRecord("test", logging.INFO, __file__, 1,
                               "password=hunter2secret api_key=abc123def", None, None)
    RedactionFilter().filter(record)
    formatted = JsonFormatter().format(record)
    payload = json.loads(formatted)
    assert "hunter2secret" not in formatted
    assert "abc123def" not in formatted
    assert "REDACTED" in payload["message"]


def test_mt5_detection_honest_on_linux():
    detection = detect_mt5(None)
    if detection.os_name != "Windows":
        assert not detection.platform_supported
        assert not detection.usable
        assert any("Windows" in n for n in detection.notes)


@pytest.mark.asyncio
async def test_mt5_adapter_refuses_gracefully():
    adapter = MT5Adapter(MT5Settings(login=1, password="x", server="s"))
    connected = await adapter.connect()
    if adapter.detection.os_name != "Windows":
        assert connected is False
        assert adapter.last_error
        assert adapter.account is None
    payload = adapter.status_payload()
    assert payload["state"] in ("DISCONNECTED", "ERROR", "CONNECTED")
    # data calls return empty, never fake
    assert await adapter.get_tick("EURUSD") is None or adapter.connected
    assert await adapter.get_candles("EURUSD", "M15") == [] or adapter.connected


def test_mask_login():
    assert mask_login(12345678) == "****5678"
    assert "1234" not in mask_login(12345678)


def test_sessions_use_real_clock():
    s = current_sessions()
    assert "utc_time" in s
    assert isinstance(s["fx_market_open"], bool)
    from datetime import datetime, timezone
    # Saturday: market closed
    saturday = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    assert current_sessions(saturday)["fx_market_open"] is False
    # Tuesday 14:00 UTC: London+NY overlap
    tuesday = datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc)
    result = current_sessions(tuesday)
    assert result["fx_market_open"] is True
    assert result["overlap"] == "London/New York overlap"


def test_calendar_warns_only_high_impact_near():
    from datetime import datetime, timedelta, timezone

    cal = EconomicCalendar(NewsSettings())
    now = datetime.now(timezone.utc)
    cal.add_event(title="CPI", currency="USD", impact="high",
                  scheduled_at=(now + timedelta(minutes=18)).isoformat())
    cal.add_event(title="Minor", currency="USD", impact="low",
                  scheduled_at=(now + timedelta(minutes=5)).isoformat())
    cal.add_event(title="Far", currency="USD", impact="high",
                  scheduled_at=(now + timedelta(hours=5)).isoformat())

    warning = cal.news_risk_for("EURUSD")
    assert warning is not None and warning["event"]["title"] == "CPI"
    assert cal.news_risk_for("EURGBP") is None  # no USD leg
    assert cal.news_risk_for("XAUUSD") is not None  # gold watches USD


def test_coach_needs_enough_trades():
    result = coach_from_journal([])
    assert result["observations"] == []
    assert "Not enough" in result["message"]


def test_coach_detects_stop_out_pattern():
    entries = [
        {"pl": -10, "sl": 1.0, "closed_at": f"2026-08-{10 + i % 5:02d}T10:00:00",
         "close_reason": "stop-loss hit", "confidence": 3}
        for i in range(15)
    ]
    result = coach_from_journal(entries)
    patterns = [o["pattern"] for o in result["observations"]]
    assert "entering before confirmation" in patterns


@pytest.mark.asyncio
async def test_database_journal_roundtrip(tmp_path):
    from app.execution.paper import ClosedTrade

    db = Database(f"sqlite+aiosqlite:///{tmp_path}/j.db")
    assert await db.start()
    trade = ClosedTrade(
        id="P1-abc", symbol="EURUSD", direction="buy", volume=0.1,
        entry=1.1, exit=1.11, sl=1.09, tp=None, pl=100.0,
        opened_at="2026-08-24T10:00:00", closed_at="2026-08-24T11:00:00",
        close_reason="manual", strategy="test", confidence=4,
    )
    await db.add_journal_entry(trade, market_conditions={"bias": "bullish"})
    entries = await db.journal_entries()
    assert len(entries) == 1
    assert entries[0]["result"] == "win"
    assert entries[0]["market_conditions"]["bias"] == "bullish"
    await db.stop()
