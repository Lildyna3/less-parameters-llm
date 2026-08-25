"""MT5 bridge protocol + access-token security.

The bridge tests matter most for honesty: they prove ARES reports CONNECTED
only when a real bridge says its terminal is live, and drops to a truthful
state the moment the bridge goes away.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import AresConfig, MarketDataSettings
from app.main import create_app
from app.mt5.bridge import BridgeDisconnected, BridgeMT5Adapter, MT5BridgeServer

BRIDGE_TOKEN = "test-bridge-secret"


@pytest.fixture
def bridge_config(tmp_path) -> AresConfig:
    config = AresConfig(environment="test")
    config.market_data = MarketDataSettings(mode="simulation", tick_interval_seconds=0.05)
    config.system.database_url = f"sqlite+aiosqlite:///{tmp_path}/bridge.db"
    config.system.serve_frontend = False
    config.news.news_feed_enabled = False
    config.bridge.token = BRIDGE_TOKEN
    return config


@pytest.fixture
def client(bridge_config):
    with TestClient(create_app(bridge_config)) as c:
        yield c


def hello(**overrides) -> str:
    payload = {
        "type": "hello", "token": BRIDGE_TOKEN, "bridge_version": "1.0.0",
        "host": "WIN-TEST (Windows 11)", "terminal_connected": True,
        "mt5_state": "CONNECTED", "detail": "", "terminal_path": r"C:\MT5\terminal64.exe",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_bridge_rejects_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/bridge/ws") as ws:
            ws.send_text(json.dumps({"type": "hello", "token": "wrong"}))
            ws.receive_text()  # server closes instead of acking


def test_bridge_attaches_and_reports_connected(client):
    # Before any bridge: honestly disconnected.
    assert client.get("/api/bridge").json()["state"] == "DISCONNECTED"

    with client.websocket_connect("/bridge/ws") as ws:
        ws.send_text(hello())
        ack = json.loads(ws.receive_text())
        assert ack["type"] == "hello_ack"

        ws.send_text(json.dumps({
            "type": "heartbeat", "terminal_connected": True, "mt5_state": "CONNECTED",
            "detail": "", "broker": "Test Broker", "server": "Test-Demo",
            "account": {"login": 12345678, "broker": "Test Broker", "server": "Test-Demo",
                        "currency": "USD", "balance": 10000.0, "equity": 10050.0,
                        "margin_free": 9000.0, "leverage": 100, "trade_allowed": True,
                        "is_demo": True},
        }))
        # Give the server loop a moment by issuing a request through the API.
        status = client.get("/api/bridge").json()
        assert status["attached"] is True
        assert status["state"] == "CONNECTED"
        assert status["bridge"]["host"].startswith("WIN-TEST")
        # Account is exposed with the login masked, never in full.
        assert status["account"]["login_masked"].endswith("5678")
        assert "12345678" not in json.dumps(status)
        assert status["account"]["is_demo"] is True

    # After the socket closes the state must fall back to the truth.
    after = client.get("/api/bridge").json()
    assert after["attached"] is False
    assert after["connected"] is False
    assert after["state"] == "DISCONNECTED"


def test_bridge_terminal_states_are_surfaced(client):
    with client.websocket_connect("/bridge/ws") as ws:
        ws.send_text(hello(terminal_connected=False, mt5_state="MT5_TERMINAL_NOT_RUNNING",
                           detail="initialize failed (-10003)"))
        ws.receive_text()
        status = client.get("/api/bridge").json()
        assert status["state"] == "MT5 TERMINAL NOT RUNNING"
        assert status["connected"] is False
        assert "-10003" in status["bridge"]["detail"]


def test_bridge_broker_disconnected_state(client):
    with client.websocket_connect("/bridge/ws") as ws:
        ws.send_text(hello(terminal_connected=False, mt5_state="BROKER_DISCONNECTED",
                           detail="no tick retrieved"))
        ws.receive_text()
        assert client.get("/api/bridge").json()["state"] == "BROKER DISCONNECTED"


def test_market_data_flows_through_the_bridge(tmp_path):
    """The whole point of the bridge: with one attached, quotes and candles are
    served from it and tagged MT5. With none, the data source is OFFLINE."""
    config = AresConfig(environment="test")
    # Real MT5 data path (not simulation) so the bridge is the only source.
    config.market_data = MarketDataSettings(mode="mt5", tick_interval_seconds=0.05)
    config.system.database_url = f"sqlite+aiosqlite:///{tmp_path}/flow.db"
    config.system.serve_frontend = False
    config.news.news_feed_enabled = False
    config.bridge.token = BRIDGE_TOKEN

    candles = [
        {"time": 1_800_000_000 + i * 900, "open": 1.085, "high": 1.0855,
         "low": 1.0845, "close": 1.0851, "volume": 600}
        for i in range(120)
    ]

    with TestClient(create_app(config)) as client:
        # No bridge: refuse rather than invent.
        assert client.get("/api/market/EURUSD").status_code == 503
        assert client.get("/api/health").json()["components"]["market_data"]["state"] == "OFFLINE"

        with client.websocket_connect("/bridge/ws") as ws:
            ws.send_text(hello())
            ws.receive_text()

            # Serve one tick request through the bridge.
            def answer(expected_method: str, result):
                request = json.loads(ws.receive_text())
                assert request["type"] == "request"
                assert request["method"] == expected_method
                ws.send_text(json.dumps({"type": "response", "id": request["id"], "result": result}))

            import threading

            tick_payload = {"symbol": "EURUSD", "bid": 1.08512, "ask": 1.08520,
                            "spread_points": 8.0, "time": "2026-08-25T02:50:00+00:00"}

            # The HTTP call blocks until the bridge answers, so answer from a thread.
            holder: dict = {}

            def fetch():
                holder["tick"] = client.get("/api/market/EURUSD")

            worker = threading.Thread(target=fetch)
            worker.start()
            # The service may probe daily references first; answer whatever it asks.
            for _ in range(6):
                request = json.loads(ws.receive_text())
                result = tick_payload if request["method"] == "tick" else candles
                ws.send_text(json.dumps({"type": "response", "id": request["id"], "result": result}))
                if holder.get("tick") is not None:
                    break
            worker.join(timeout=10)

            response = holder["tick"]
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["bid"] == 1.08512
            assert body["source"] == "MT5"  # never SIMULATED when the bridge serves

        # Bridge gone: back to the truth immediately.
        assert client.get("/api/bridge").json()["connected"] is False


@pytest.mark.asyncio
async def test_adapter_returns_nothing_without_bridge():
    from app.config import BridgeSettings

    server = MT5BridgeServer(BridgeSettings(token="x"))
    adapter = BridgeMT5Adapter(server)
    assert adapter.connected is False
    assert await adapter.get_tick("EURUSD") is None
    assert await adapter.get_candles("EURUSD", "M15") == []
    assert await adapter.get_symbols() == []
    with pytest.raises(BridgeDisconnected):
        await server.call("tick", {"symbol": "EURUSD"})


def test_bridge_status_without_token_says_auth_required(tmp_path):
    config = AresConfig(environment="test")
    config.market_data = MarketDataSettings(mode="simulation", tick_interval_seconds=0.05)
    config.system.database_url = f"sqlite+aiosqlite:///{tmp_path}/nb.db"
    config.system.serve_frontend = False
    config.news.news_feed_enabled = False
    config.bridge.token = None
    with TestClient(create_app(config)) as c:
        status = c.get("/api/bridge").json()
        assert status["state"] == "AUTHENTICATION REQUIRED"
        assert status["token_configured"] is False


# -- access control -----------------------------------------------------------

@pytest.fixture
def secured_client(tmp_path):
    config = AresConfig(environment="test")
    config.market_data = MarketDataSettings(mode="simulation", tick_interval_seconds=0.05)
    config.system.database_url = f"sqlite+aiosqlite:///{tmp_path}/sec.db"
    config.system.serve_frontend = False
    config.news.news_feed_enabled = False
    config.security.access_token = "s3cret-access"
    with TestClient(create_app(config)) as c:
        yield c


def test_api_requires_token_when_configured(secured_client):
    assert secured_client.get("/api/status").status_code == 401
    assert secured_client.get("/api/positions").status_code == 401
    # Health stays public for uptime checks.
    assert secured_client.get("/api/health").status_code == 200


def test_api_accepts_valid_token(secured_client):
    headers = {"X-ARES-Token": "s3cret-access"}
    assert secured_client.get("/api/status", headers=headers).status_code == 200
    bearer = {"Authorization": "Bearer s3cret-access"}
    assert secured_client.get("/api/status", headers=bearer).status_code == 200
    assert secured_client.get("/api/status", headers={"X-ARES-Token": "wrong"}).status_code == 401


def test_websocket_requires_token(secured_client):
    with pytest.raises(Exception):
        with secured_client.websocket_connect("/ws") as ws:
            ws.receive_text()
    with secured_client.websocket_connect("/ws?access_token=s3cret-access") as ws:
        ws.send_text("ping")  # accepted
