"""Centralized ARES configuration.

Every subsystem reads its settings from ARES_CONFIG (an AresConfig instance).
Values come from environment variables / a local .env file. Secrets are never
hard-coded and never logged; see logging_setup.py for redaction.

Env naming: sections are flattened with an ARES_ prefix where sensible, and
MT5 credentials use the conventional MT5_* names required by the spec.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class MT5Settings(BaseModel):
    login: int | None = None
    password: str | None = None  # never logged, never sent to the frontend/AI
    server: str | None = None
    path: str | None = None  # explicit terminal path; auto-detect if empty
    reconnect_interval_seconds: float = 10.0

    @property
    def credentials_configured(self) -> bool:
        return bool(self.login and self.password and self.server)


class MarketDataSettings(BaseModel):
    # "mt5"        -> only real MT5 data; OFFLINE when MT5 is unavailable.
    # "simulation" -> explicitly-enabled simulated feed for demo/testing.
    #                 Every payload it produces is labeled source="SIMULATED".
    mode: Literal["mt5", "simulation"] = "mt5"
    tick_interval_seconds: float = 1.0
    candle_cache_size: int = 1500
    default_symbols: list[str] = Field(
        default_factory=lambda: [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD",
            "USDCAD", "EURGBP", "EURJPY", "GBPJPY", "XAUUSD", "XAGUSD",
        ]
    )


class RiskSettings(BaseModel):
    max_daily_loss: float = 500.0            # account currency
    max_drawdown_percent: float = 10.0
    max_open_positions: int = 5
    max_exposure_lots: float = 5.0
    max_trades_per_session: int = 15
    max_position_size_lots: float = 1.0
    max_spread_points: float = 40.0
    cooldown_seconds_after_loss: float = 60.0
    emergency_stop_engaged: bool = False


class ExecutionSettings(BaseModel):
    # Live execution is architecturally present but hard-disabled by default.
    # Flipping this env var alone is NOT enough to trade real money: the
    # execution engine additionally requires a verified DEMO account for any
    # order and refuses live accounts outright in this build.
    live_trading_enabled: bool = False
    paper_starting_balance: float = 10000.0
    paper_currency: str = "USD"


class TakeoverSettings(BaseModel):
    max_trades: int = 3
    max_total_risk: float = 150.0            # account currency
    max_duration_seconds: int = 3600
    authorization_ttl_seconds: int = 300     # unused authorizations expire


class AISettings(BaseModel):
    provider: Literal["none", "gemini", "openai", "anthropic"] = "none"
    api_key: str | None = None               # never logged
    model: str | None = None
    timeout_seconds: float = 30.0


class NewsSettings(BaseModel):
    web_intelligence_enabled: bool = False
    calendar_warning_window_minutes: int = 30
    # Live RSS news ingestion. Requires outbound HTTPS to the news hosts; when
    # egress is blocked ARES reports the feed OFFLINE instead of inventing news.
    news_feed_enabled: bool = True
    refresh_interval_seconds: int = 300
    fetch_timeout_seconds: float = 12.0
    max_articles: int = 300
    # Operator-supplied feeds, as JSON:
    #   [{"id":"x","name":"X","url":"https://…","categories":["FOREX"]}]
    # Added to the built-in list, or used alone when replace_default_feeds is on.
    extra_feeds: list[dict] = Field(default_factory=list)
    replace_default_feeds: bool = False


class BridgeSettings(BaseModel):
    """Windows MT5 bridge. The bridge process connects OUT to this backend over
    an authenticated WebSocket, so the Linux/cloud host never needs the
    Windows-only MetaTrader5 package."""

    enabled: bool = True
    # Shared secret the bridge presents on connect. Empty = bridge refused.
    token: str | None = None
    heartbeat_interval_seconds: float = 15.0
    # A bridge that misses this many seconds of heartbeats is considered gone.
    stale_after_seconds: float = 45.0
    request_timeout_seconds: float = 20.0


class SecuritySettings(BaseModel):
    """Optional access control for the deployed web app. When an access token
    is configured, API and WebSocket clients must present it. The token lives
    only in the server environment and the browser's local storage — it is
    never baked into the frontend bundle."""

    access_token: str | None = None
    # Paths always reachable without a token (health/status for uptime checks).
    public_paths: list[str] = Field(default_factory=lambda: ["/api/health"])


class SystemSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    database_url: str = f"sqlite+aiosqlite:///{BACKEND_DIR / 'data' / 'ares.db'}"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    # In production the backend serves the built frontend from this directory,
    # so one process and one URL serve phone, laptop and desktop alike.
    serve_frontend: bool = True
    frontend_dist: str = str(PROJECT_DIR / "frontend" / "dist")


class AresConfig(BaseSettings):
    """Root configuration. Nested sections map to env vars via `__` delimiter,
    e.g. ARES_RISK__MAX_DAILY_LOSS=250. MT5 credentials additionally accept the
    plain MT5_LOGIN / MT5_PASSWORD / MT5_SERVER / MT5_PATH names."""

    model_config = SettingsConfigDict(
        env_prefix="ARES_",
        env_nested_delimiter="__",
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "production", "test"] = "development"
    mt5: MT5Settings = Field(default_factory=MT5Settings)
    market_data: MarketDataSettings = Field(default_factory=MarketDataSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    takeover: TakeoverSettings = Field(default_factory=TakeoverSettings)
    ai: AISettings = Field(default_factory=AISettings)
    news: NewsSettings = Field(default_factory=NewsSettings)
    bridge: BridgeSettings = Field(default_factory=BridgeSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    system: SystemSettings = Field(default_factory=SystemSettings)

    def model_post_init(self, __context) -> None:
        # Conventional MT5_* env names (per spec / .env.example) override the
        # nested form when present.
        import os

        if os.getenv("MT5_LOGIN"):
            try:
                self.mt5.login = int(os.environ["MT5_LOGIN"])
            except ValueError:
                self.mt5.login = None
        if os.getenv("MT5_PASSWORD"):
            self.mt5.password = os.environ["MT5_PASSWORD"]
        if os.getenv("MT5_SERVER"):
            self.mt5.server = os.environ["MT5_SERVER"]
        if os.getenv("MT5_PATH"):
            self.mt5.path = os.environ["MT5_PATH"]
        # Conventional names for the bridge/access secrets.
        if os.getenv("ARES_BRIDGE_TOKEN"):
            self.bridge.token = os.environ["ARES_BRIDGE_TOKEN"]
        if os.getenv("ARES_ACCESS_TOKEN"):
            self.security.access_token = os.environ["ARES_ACCESS_TOKEN"]
        # Same convenience for AI keys.
        if os.getenv("GEMINI_API_KEY") and self.ai.provider == "gemini":
            self.ai.api_key = self.ai.api_key or os.environ["GEMINI_API_KEY"]
        if os.getenv("OPENAI_API_KEY") and self.ai.provider == "openai":
            self.ai.api_key = self.ai.api_key or os.environ["OPENAI_API_KEY"]
        if os.getenv("ANTHROPIC_API_KEY") and self.ai.provider == "anthropic":
            self.ai.api_key = self.ai.api_key or os.environ["ANTHROPIC_API_KEY"]


@lru_cache
def get_config() -> AresConfig:
    return AresConfig()


def reset_config_cache() -> None:
    """Used by tests to re-read the environment."""
    get_config.cache_clear()
