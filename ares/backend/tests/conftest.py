import asyncio

import pytest

from app.config import (
    AresConfig,
    ExecutionSettings,
    MarketDataSettings,
    RiskSettings,
    TakeoverSettings,
)
from app.execution.baskets import BasketManager
from app.execution.paper import PaperTradingEngine
from app.execution.takeover import TakeoverManager
from app.market_data.providers import SimulatedProvider
from app.market_data.service import MarketDataService
from app.risk.engine import RiskEngine


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def market_data() -> MarketDataService:
    return MarketDataService(SimulatedProvider(seed=7), MarketDataSettings(mode="simulation"))


@pytest.fixture
def risk() -> RiskEngine:
    return RiskEngine(RiskSettings())


@pytest.fixture
def paper(market_data, risk) -> PaperTradingEngine:
    return PaperTradingEngine(market_data, risk, ExecutionSettings())


@pytest.fixture
def baskets(paper) -> BasketManager:
    return BasketManager(paper)


@pytest.fixture
def takeover(paper, baskets) -> TakeoverManager:
    return TakeoverManager(paper, baskets, TakeoverSettings())


@pytest.fixture
def client_factory(test_config):
    """Builds a TestClient over the full app (news fetching disabled so tests
    never touch the network)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    created = []

    def _factory():
        client = TestClient(create_app(test_config))
        client.__enter__()
        created.append(client)
        return client

    yield _factory
    for client in created:
        client.__exit__(None, None, None)


@pytest.fixture
def test_config(tmp_path) -> AresConfig:
    config = AresConfig(environment="test")
    config.market_data = MarketDataSettings(mode="simulation", tick_interval_seconds=0.05)
    config.system.database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    config.system.serve_frontend = False   # tests exercise the API, not the SPA
    config.news.news_feed_enabled = False  # never touch the network in tests
    return config
