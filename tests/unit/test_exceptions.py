"""Unit tests for the exception hierarchy."""


from stockfeed.exceptions import (
    CacheError,
    CacheReadError,
    CacheWriteError,
    ConfigurationError,
    DevModeError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    StockFeedError,
    TickerNotFoundError,
    UnsupportedIntervalError,
    ValidationError,
)


class TestExceptionHierarchy:
    def test_base_fields(self) -> None:
        err = StockFeedError("Something went wrong", provider="tiingo", ticker="AAPL")
        assert err.message == "Something went wrong"
        assert err.provider == "tiingo"
        assert err.ticker == "AAPL"
        assert err.suggestion is None

    def test_str_includes_all_fields(self) -> None:
        err = StockFeedError(
            "Oops", provider="tiingo", ticker="AAPL", suggestion="Try again later"
        )
        s = str(err)
        assert "Oops" in s
        assert "tiingo" in s
        assert "AAPL" in s
        assert "Try again later" in s

    def test_provider_error_is_stockfeed_error(self) -> None:
        err = ProviderError("provider failed")
        assert isinstance(err, StockFeedError)

    def test_rate_limit_error_has_retry_after(self) -> None:
        err = ProviderRateLimitError("rate limited", provider="finnhub", retry_after=60.0)
        assert err.retry_after == 60.0
        assert isinstance(err, ProviderError)

    def test_cache_errors_inherit_from_cache_error(self) -> None:
        assert issubclass(CacheReadError, CacheError)
        assert issubclass(CacheWriteError, CacheError)

    def test_all_leaf_exceptions_are_stockfeed_errors(self) -> None:
        for cls in [
            ProviderAuthError,
            ProviderRateLimitError,
            ProviderUnavailableError,
            TickerNotFoundError,
            CacheReadError,
            CacheWriteError,
            ValidationError,
            UnsupportedIntervalError,
            ConfigurationError,
            DevModeError,
        ]:
            assert issubclass(cls, StockFeedError), f"{cls} is not a StockFeedError"
