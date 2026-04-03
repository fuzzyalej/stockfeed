"""Integration tests for provider failover chain and market hours cache bypass."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from stockfeed.client import StockFeedClient
from stockfeed.config import StockFeedSettings
from stockfeed.exceptions import ProviderRateLimitError, ProviderUnavailableError
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bar(ticker: str = "AAPL", days_offset: int = 0) -> OHLCVBar:
    ts = datetime(2024, 1, 1 + days_offset, tzinfo=timezone.utc)
    return OHLCVBar(
        ticker=ticker,
        timestamp=ts,
        interval=Interval.ONE_DAY,
        open=Decimal("185.50"),
        high=Decimal("188.44"),
        low=Decimal("183.00"),
        close_raw=Decimal("187.20"),
        close_adj=Decimal("187.20"),
        volume=1_000_000,
        vwap=None,
        trade_count=None,
        provider="yfinance",
    )


def _settings(tmp_path: object) -> StockFeedSettings:
    return StockFeedSettings(
        cache_path=str(tmp_path / "cache.db"),  # type: ignore[operator]
        cache_enabled=True,
        log_level="WARNING",
    )


# ---------------------------------------------------------------------------
# Failover chain
# ---------------------------------------------------------------------------


class TestFailoverChain:
    """Verify provider-level failover falls through to yfinance."""

    def test_client_falls_back_to_yfinance_when_first_provider_raises(
        self, tmp_path: object
    ) -> None:
        """When the preferred provider raises ProviderUnavailableError the client
        retries with the next provider in the chain (yfinance)."""
        settings = _settings(tmp_path)
        client = StockFeedClient(settings=settings)

        bars = [_make_bar(days_offset=i) for i in range(3)]

        # Build two providers: first raises, second succeeds
        failing_provider = MagicMock()
        failing_provider.name = "failing"
        failing_provider.supported_intervals = list(Interval)
        failing_provider.get_ohlcv.side_effect = ProviderUnavailableError(
            "Simulated failure", provider="failing"
        )

        succeeding_provider = MagicMock()
        succeeding_provider.name = "yfinance"
        succeeding_provider.supported_intervals = list(Interval)
        succeeding_provider.get_ohlcv.return_value = bars

        with patch.object(
            client._selector, "select", return_value=[failing_provider, succeeding_provider]
        ):
            result = client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-04")

        # yfinance was called after the first provider failed
        failing_provider.get_ohlcv.assert_called_once()
        succeeding_provider.get_ohlcv.assert_called_once()
        assert len(result) == 3

    def test_client_raises_when_all_providers_fail(self, tmp_path: object) -> None:
        """When every provider in the chain fails, ProviderUnavailableError is raised."""
        settings = _settings(tmp_path)
        client = StockFeedClient(settings=settings)

        failing1 = MagicMock()
        failing1.name = "p1"
        failing1.get_ohlcv.side_effect = ProviderUnavailableError("fail1", provider="p1")

        failing2 = MagicMock()
        failing2.name = "p2"
        failing2.get_ohlcv.side_effect = ProviderUnavailableError("fail2", provider="p2")

        with (
            patch.object(client._selector, "select", return_value=[failing1, failing2]),
            pytest.raises(ProviderUnavailableError),
        ):
            client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-04")

    def test_rate_limit_error_causes_failover(self, tmp_path: object) -> None:
        """A rate-limited provider should cause the client to try the next one."""
        settings = _settings(tmp_path)
        client = StockFeedClient(settings=settings)

        bars = [_make_bar()]
        rate_limited = MagicMock()
        rate_limited.name = "rate_limited"
        rate_limited.get_ohlcv.side_effect = ProviderRateLimitError(
            "Rate limited", provider="rate_limited", retry_after=60.0
        )

        fallback = MagicMock()
        fallback.name = "fallback"
        fallback.get_ohlcv.return_value = bars

        with patch.object(client._selector, "select", return_value=[rate_limited, fallback]):
            result = client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-02")

        assert len(result) == 1
        fallback.get_ohlcv.assert_called_once()

    def test_auth_error_does_not_failover(self, tmp_path: object) -> None:
        """ProviderAuthError propagates immediately — no failover attempted."""
        from stockfeed.exceptions import ProviderAuthError

        settings = _settings(tmp_path)
        client = StockFeedClient(settings=settings)

        auth_failing = MagicMock()
        auth_failing.name = "auth_failing"
        auth_failing.get_ohlcv.side_effect = ProviderAuthError("Bad key", provider="auth_failing")

        fallback = MagicMock()
        fallback.name = "fallback"
        fallback.get_ohlcv.return_value = [_make_bar()]

        with (
            patch.object(client._selector, "select", return_value=[auth_failing, fallback]),
            pytest.raises(ProviderAuthError),
        ):
            client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-02")

        # Fallback must NOT have been called
        fallback.get_ohlcv.assert_not_called()

    def test_provider_unavailable_error_from_400_causes_failover(self, tmp_path: object) -> None:
        """ProviderUnavailableError (mapped from HTTP 400) triggers failover."""
        settings = _settings(tmp_path)
        client = StockFeedClient(settings=settings)

        bars = [_make_bar()]
        unavailable = MagicMock()
        unavailable.name = "tradier"
        unavailable.get_ohlcv.side_effect = ProviderUnavailableError(
            "Tradier HTTP 400 (no market data)", provider="tradier"
        )

        fallback = MagicMock()
        fallback.name = "yfinance"
        fallback.get_ohlcv.return_value = bars

        with patch.object(client._selector, "select", return_value=[unavailable, fallback]):
            result = client.get_ohlcv("GME", "1m", "2024-01-02", "2024-01-03")

        assert len(result) == 1
        fallback.get_ohlcv.assert_called_once()


# ---------------------------------------------------------------------------
# Market hours cache bypass
# ---------------------------------------------------------------------------


class TestMarketHoursCacheBypass:
    """Cache must be bypassed for intraday intervals during market hours."""

    def test_cache_bypassed_during_market_hours_intraday(self, tmp_path: object) -> None:
        """When market is open, intraday bars must be fetched fresh even if cache has data."""
        settings = _settings(tmp_path)
        client = StockFeedClient(settings=settings)

        # Seed cache with a 1m bar
        intraday_bar = OHLCVBar(
            ticker="AAPL",
            timestamp=datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
            interval=Interval.ONE_MINUTE,
            open=Decimal("185"),
            high=Decimal("186"),
            low=Decimal("184"),
            close_raw=Decimal("185.50"),
            close_adj=None,
            volume=1000,
            vwap=None,
            trade_count=None,
            provider="yfinance",
        )
        if client._cache:
            client._cache.write([intraday_bar])

        # Market is open — should_use_cache returns False
        fresh_bar = OHLCVBar(
            ticker="AAPL",
            timestamp=datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
            interval=Interval.ONE_MINUTE,
            open=Decimal("186"),  # different open — proves it came from provider
            high=Decimal("187"),
            low=Decimal("185"),
            close_raw=Decimal("186.50"),
            close_adj=None,
            volume=2000,
            vwap=None,
            trade_count=None,
            provider="yfinance",
        )

        mock_provider = MagicMock()
        mock_provider.name = "yfinance"
        mock_provider.get_ohlcv.return_value = [fresh_bar]

        with (
            patch.object(client._market_hours, "should_use_cache", return_value=False),
            patch.object(client._selector, "select", return_value=[mock_provider]),
        ):
            result = client.get_ohlcv("AAPL", "1m", "2024-01-02", "2024-01-03")

        mock_provider.get_ohlcv.assert_called_once()
        assert result[0].open == Decimal("186")  # from provider, not cache

    def test_cache_used_outside_market_hours(self, tmp_path: object) -> None:
        """Outside market hours, even intraday bars are served from cache."""
        settings = _settings(tmp_path)
        client = StockFeedClient(settings=settings)

        cached_bar = OHLCVBar(
            ticker="AAPL",
            timestamp=datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
            interval=Interval.ONE_MINUTE,
            open=Decimal("185"),
            high=Decimal("186"),
            low=Decimal("184"),
            close_raw=Decimal("185.50"),
            close_adj=None,
            volume=1000,
            vwap=None,
            trade_count=None,
            provider="yfinance",
        )
        if client._cache:
            client._cache.write([cached_bar])

        mock_provider = MagicMock()

        start = datetime(2024, 1, 2, 14, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, 15, 0, tzinfo=timezone.utc)

        with (
            patch.object(client._market_hours, "should_use_cache", return_value=True),
            patch.object(client._selector, "select", return_value=[mock_provider]),
            patch.object(client._cache, "read", return_value=[cached_bar]),  # type: ignore[union-attr]
        ):
            result = client.get_ohlcv("AAPL", "1m", start, end)

        mock_provider.get_ohlcv.assert_not_called()
        assert len(result) == 1
        assert result[0].open == Decimal("185")  # from cache

    def test_daily_bars_always_served_from_cache(self, tmp_path: object) -> None:
        """Daily interval bars should always be served from cache when present."""
        settings = _settings(tmp_path)
        client = StockFeedClient(settings=settings)

        cached_bars = [_make_bar(days_offset=i) for i in range(3)]
        if client._cache:
            client._cache.write(cached_bars)

        mock_provider = MagicMock()

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            result = client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-04")

        # Provider not called — all data came from cache
        mock_provider.get_ohlcv.assert_not_called()
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Partial cache hit
# ---------------------------------------------------------------------------


class TestPartialCacheHit:
    """Verify the client writes provider data back into cache after a miss."""

    def test_cache_written_after_provider_fetch(self, tmp_path: object) -> None:
        """After a cache miss, newly fetched bars are stored in the cache."""
        settings = _settings(tmp_path)
        client = StockFeedClient(settings=settings)

        bars = [_make_bar(days_offset=i) for i in range(3)]

        mock_provider = MagicMock()
        mock_provider.name = "yfinance"
        mock_provider.get_ohlcv.return_value = bars

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-04")

        # Now the same request should hit cache and NOT call the provider again
        mock_provider.get_ohlcv.reset_mock()

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            cached_result = client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-04")

        mock_provider.get_ohlcv.assert_not_called()
        assert len(cached_result) == 3
