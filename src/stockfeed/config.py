"""Configuration system for stockfeed using pydantic-settings."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class StockFeedSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STOCKFEED_", env_file=".env", extra="ignore")

    # Provider API keys — all optional, presence determines availability
    tiingo_api_key: str | None = None
    finnhub_api_key: str | None = None
    twelvedata_api_key: str | None = None
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    tradier_api_key: str | None = None
    coingecko_api_key: str | None = None  # Optional (free tier exists)

    # Cache
    cache_path: str = "~/.stockfeed/cache.db"
    cache_enabled: bool = True

    # Dev mode
    dev_mode: bool = False

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"
