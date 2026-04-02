"""Unit tests for StockFeedSettings."""

from stockfeed.config import StockFeedSettings


class TestStockFeedSettings:
    def test_defaults(self) -> None:
        s = StockFeedSettings()
        assert s.cache_path == "~/.stockfeed/cache.db"
        assert s.cache_enabled is True
        assert s.dev_mode is False
        assert s.log_level == "INFO"
        assert s.log_format == "console"

    def test_no_api_keys_by_default(self) -> None:
        s = StockFeedSettings()
        assert s.tiingo_api_key is None
        assert s.finnhub_api_key is None
        assert s.twelvedata_api_key is None
        assert s.alpaca_api_key is None
        assert s.alpaca_secret_key is None
        assert s.tradier_api_key is None
        assert s.coingecko_api_key is None

    def test_override_via_kwargs(self) -> None:
        s = StockFeedSettings(dev_mode=True, log_level="DEBUG", log_format="json")
        assert s.dev_mode is True
        assert s.log_level == "DEBUG"
        assert s.log_format == "json"

    def test_env_prefix(self) -> None:
        assert StockFeedSettings.model_config.get("env_prefix") == "STOCKFEED_"
