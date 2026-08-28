"""API + integration tests over the full app (simulation market data)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(test_config):
    app = create_app(test_config)
    with TestClient(app) as c:
        yield c


def test_health_and_status(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["components"]["mt5"]["state"] == "OFFLINE"  # truthful on Linux
    assert body["components"]["execution"]["detail"]["mode"] == "PAPER"

    status = client.get("/api/status").json()
    assert "sessions" in status
    assert status["components"]["market_data"]["detail"]["source"] == "SIMULATED"


def test_mt5_truthfully_offline(client):
    """On a host that cannot drive MT5 directly, ARES reports the bridge path
    as genuinely unattached — never a fake connection."""
    account = client.get("/api/account").json()
    mt5 = account["mt5"]
    assert mt5["account"] is None
    assert mt5["mode"] == "bridge"
    assert mt5["attached"] is False
    assert mt5["connected"] is False
    assert mt5["state"] in ("DISCONNECTED", "AUTHENTICATION REQUIRED", "DISABLED")

    bridge = client.get("/api/bridge").json()
    assert bridge["access_mode"] == "bridge"
    assert bridge["connected"] is False
    assert "MT5_BRIDGE" in bridge["instructions"] or "bridge" in bridge["instructions"]


def test_market_and_candles(client):
    tick = client.get("/api/market/EURUSD").json()
    assert tick["source"] == "SIMULATED"
    assert tick["ask"] > tick["bid"]

    candles = client.get("/api/candles/EURUSD?timeframe=M15&count=100").json()
    assert candles["source"] == "SIMULATED"
    assert len(candles["candles"]) == 100
    assert candles["candles"][0]["time"] < candles["candles"][-1]["time"]

    missing = client.get("/api/market/NOSYMBOL")
    assert missing.status_code == 503
    assert "OFFLINE" in missing.json()["detail"]


def test_analyze_endpoint(client):
    resp = client.post("/api/analyze", json={"symbol": "XAUUSD"})
    assert resp.status_code == 200
    analysis = resp.json()["analysis"]
    assert analysis["symbol"] == "XAUUSD"
    assert 1 <= analysis["confidence"] <= 5
    assert analysis["data_source"] == "SIMULATED"


def test_order_flow_and_positions(client):
    validate = client.post("/api/order/validate", json={
        "symbol": "EURUSD", "direction": "buy", "volume": 0.1}).json()
    assert validate["success"]

    order = client.post("/api/order/demo", json={
        "symbol": "EURUSD", "direction": "buy", "volume": 0.1, "strategy": "api-test"}).json()
    assert order["success"]
    pos_id = order["position"]["id"]

    positions = client.get("/api/positions").json()
    assert len(positions["positions"]) == 1

    close = client.post("/api/position/close", json={"position_id": pos_id}).json()
    assert close["success"]

    trades = client.get("/api/trades").json()
    assert len(trades["trades"]) == 1

    journal = client.get("/api/journal").json()
    assert len(journal["entries"]) == 1
    assert journal["entries"][0]["trade_id"] == pos_id


def test_risk_endpoints(client):
    risk = client.get("/api/risk").json()
    assert risk["emergency_stop"] is False

    update = client.post("/api/risk/limits", json={"max_daily_loss": 250}).json()
    assert update["risk"]["limits"]["max_daily_loss"] == 250

    stop = client.post("/api/risk/emergency-stop").json()
    assert stop["engaged"]
    blocked = client.post("/api/order/demo", json={
        "symbol": "EURUSD", "direction": "buy", "volume": 0.1}).json()
    assert not blocked["success"]

    client.post("/api/risk/emergency-stop/release")
    assert client.get("/api/risk").json()["emergency_stop"] is False


def test_takeover_endpoints_require_explicit_confirm(client):
    request = client.post("/api/takeover/request", json={
        "symbol": "EURUSD", "direction": "buy", "reason": "test", "confidence": 4,
        "proposed_trades": [{"symbol": "EURUSD", "direction": "buy",
                             "volume": 0.05, "sl": 1.0, "tp": 1.2}],
    }).json()
    assert request["success"]
    session_id = request["session"]["id"]

    no_confirm = client.post("/api/takeover/authorize", json={"session_id": session_id})
    assert no_confirm.status_code == 400

    auth = client.post("/api/takeover/authorize",
                       json={"session_id": session_id, "confirm": True}).json()
    assert auth["success"]

    stop = client.post("/api/takeover/stop").json()
    assert stop["success"]


def test_command_center(client):
    reply = client.post("/api/command", json={"message": "Analyze XAUUSD"}).json()
    assert "XAUUSD" in reply["reply"]
    assert reply["analysis"]["confidence"] in range(1, 6)
    assert "SIMULATED" in reply["reply"]  # honesty about the demo feed

    followup = client.post("/api/command", json={"message": "Why is your confidence that high?"}).json()
    assert "confidence" in followup["reply"].lower()

    scan = client.post("/api/command", json={"message": "Scan the market"}).json()
    assert "Scanned" in scan["reply"]

    status = client.post("/api/command", json={"message": "status"}).json()
    assert "MT5" in status["reply"]

    chat_auth = client.post("/api/command", json={"message": "authorize takeover"}).json()
    assert "can't" in chat_auth["reply"].lower() or "explicit" in chat_auth["reply"].lower()


def test_calendar_and_news_warning(client):
    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    event = client.post("/api/calendar/events", json={
        "title": "NFP", "currency": "USD", "impact": "high", "scheduled_at": soon}).json()
    assert event["event"]["impact"] == "high"

    analysis = client.post("/api/analyze", json={"symbol": "EURUSD"}).json()
    assert analysis["news_warning"] is not None
    assert "minutes" in analysis["news_warning"]["warning"]


def test_alerts_crud(client):
    alert = client.post("/api/alerts/price", json={
        "symbol": "EURUSD", "level": 999.0, "condition": "above"}).json()
    listing = client.get("/api/alerts").json()
    assert any(a["id"] == alert["alert"]["id"] for a in listing["price_alerts"])
    deleted = client.delete(f"/api/alerts/price/{alert['alert']['id']}")
    assert deleted.status_code == 200


def test_scanner_and_analytics(client):
    scan = client.get("/api/scanner").json()
    assert scan["results"]
    assert all(r["data_source"] == "SIMULATED" for r in scan["results"])

    analytics = client.get("/api/analytics").json()
    assert analytics["account"]["mode"] == "PAPER"
    assert "analyses_performed" in analytics["ares"]

    coach = client.get("/api/coach").json()
    assert "trades_analyzed" in coach


def test_websocket_connects(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text("ping")
    # No exception = pass; status endpoint should have seen the client.
