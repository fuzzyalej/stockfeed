"""Unit tests for StockFeedClient — failover, cache, and provider-pinning."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from stockfeed import AsyncStockFeedClient, StockFeedClient
from stockfeed.config import StockFeedSettings
from stockfeed.exceptions import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    TickerNotFoundError,
)
from stockfeed.models.health import HealthStatus
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 2, tzinfo=timezone.utc)


def _bar(ticker: str = "AAPL") -> OHLCVBar:
    return OHLCVBar(
        ticker=ticker,
        provider="yfinance",
        interval=Interval.ONE_DAY,
        timestamp=_TS,
        open=Decimal("185"),
        high=Decimal("186"),
        low=Decimal("184"),
        close_raw=Decimal("185.5"),
        close_adj=None,
        volume=1_000_000,
        vwap=None,
        trade_count=None,
    )


def _quote(ticker: str = "AAPL") -> Quote:
    return Quote(
        ticker=ticker,
        provider="yfinance",
        timestamp=_TS,
        last=Decimal("185.5"),
        bid=None,
        ask=None,
        bid_size=None,
        ask_size=None,
        last_size=None,
        volume=None,
        open=None,
        high=None,
        low=None,
        close=None,
        change=None,
        change_pct=None,
    )


def _health(provider: str = "yfinance") -> HealthStatus:
    return HealthStatus(
        provider=provider,
        healthy=True,
        latency_ms=12.0,
        error=None,
        checked_at=_TS,
        rate_limit_remaining=None,
    )


def _make_client(tmp_db_path: str) -> StockFeedClient:
    settings = StockFeedSettings(
        cache_path=tmp_db_path,
        cache_enabled=True,
        log_level="WARNING",
    )
    return StockFeedClient(settings=settings)


def _make_async_client(tmp_db_path: str) -> AsyncStockFeedClient:
    settings = StockFeedSettings(
        cache_path=tmp_db_path,
        cache_enabled=True,
        log_level="WARNING",
    )
    return AsyncStockFeedClient(settings=settings)


# ---------------------------------------------------------------------------
# get_ohlcv — basic happy path
# ---------------------------------------------------------------------------

class TestGetOhlcv:
    def test_returns_bars_from_provider(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        bars = [_bar()]

        mock_provider = MagicMock()
        mock_provider.get_ohlcv.return_value = bars

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            result = client.get_ohlcv(
                "AAPL",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 31, tzinfo=timezone.utc),
            )

        assert result == bars
        mock_provider.get_ohlcv.assert_called_once()

    def test_writes_to_cache_after_fetch(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        bars = [_bar()]

        mock_provider = MagicMock()
        mock_provider.get_ohlcv.return_value = bars

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            client.get_ohlcv(
                "AAPL",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 31, tzinfo=timezone.utc),
            )

        assert client._cache is not None
        from datetime import timedelta
        cached = client._cache.read("AAPL", Interval.ONE_DAY, _TS, _TS + timedelta(days=1))
        assert cached is not None

    def test_returns_cached_data_on_second_call(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        bars = [_bar()]

        mock_provider = MagicMock()
        mock_provider.get_ohlcv.return_value = bars

        from datetime import timedelta
        end = _TS + timedelta(days=1)
        with patch.object(client._selector, "select", return_value=[mock_provider]):
            client.get_ohlcv("AAPL", Interval.ONE_DAY, _TS, end)
            client.get_ohlcv("AAPL", Interval.ONE_DAY, _TS, end)

        # Provider called only once — second call served from cache
        assert mock_provider.get_ohlcv.call_count == 1


# ---------------------------------------------------------------------------
# get_ohlcv — failover
# ---------------------------------------------------------------------------

class TestOhlcvFailover:
    def test_falls_over_to_next_provider_on_rate_limit(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        bars = [_bar()]

        failing = MagicMock()
        failing.get_ohlcv.side_effect = ProviderRateLimitError("rate limited", provider="p1")

        succeeding = MagicMock()
        succeeding.get_ohlcv.return_value = bars

        with patch.object(client._selector, "select", return_value=[failing, succeeding]):
            result = client.get_ohlcv(
                "AAPL",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 31, tzinfo=timezone.utc),
            )

        assert result == bars
        failing.get_ohlcv.assert_called_once()
        succeeding.get_ohlcv.assert_called_once()

    def test_falls_over_on_provider_unavailable(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        bars = [_bar()]

        failing = MagicMock()
        failing.get_ohlcv.side_effect = ProviderUnavailableError("down", provider="p1")

        succeeding = MagicMock()
        succeeding.get_ohlcv.return_value = bars

        with patch.object(client._selector, "select", return_value=[failing, succeeding]):
            result = client.get_ohlcv(
                "AAPL",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 31, tzinfo=timezone.utc),
            )

        assert result == bars

    def test_raises_provider_unavailable_when_all_fail(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)

        p1 = MagicMock()
        p1.get_ohlcv.side_effect = ProviderUnavailableError("down", provider="p1")
        p2 = MagicMock()
        p2.get_ohlcv.side_effect = ProviderRateLimitError("rate limited", provider="p2")

        with patch.object(client._selector, "select", return_value=[p1, p2]), pytest.raises(ProviderUnavailableError):
            client.get_ohlcv(
                "AAPL",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 31, tzinfo=timezone.utc),
            )

    def test_auth_error_propagates_immediately(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)

        p1 = MagicMock()
        p1.get_ohlcv.side_effect = ProviderAuthError("bad key", provider="p1")
        p2 = MagicMock()
        p2.get_ohlcv.return_value = [_bar()]

        with patch.object(client._selector, "select", return_value=[p1, p2]), pytest.raises(ProviderAuthError):
            client.get_ohlcv(
                "AAPL",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 31, tzinfo=timezone.utc),
            )

        p2.get_ohlcv.assert_not_called()

    def test_ticker_not_found_propagates_immediately(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)

        p1 = MagicMock()
        p1.get_ohlcv.side_effect = TickerNotFoundError("not found", ticker="BOGUS", provider="p1")

        with patch.object(client._selector, "select", return_value=[p1]), pytest.raises(TickerNotFoundError):
            client.get_ohlcv(
                "BOGUS",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 31, tzinfo=timezone.utc),
            )


# ---------------------------------------------------------------------------
# get_quote
# ---------------------------------------------------------------------------

class TestGetQuote:
    def test_returns_quote(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        expected = _quote()

        mock_provider = MagicMock()
        mock_provider.get_quote.return_value = expected

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            result = client.get_quote("AAPL")

        assert result == expected

    def test_failover_on_unavailable(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)

        p1 = MagicMock()
        p1.get_quote.side_effect = ProviderUnavailableError("down", provider="p1")
        p2 = MagicMock()
        p2.get_quote.return_value = _quote()

        with patch.object(client._selector, "select", return_value=[p1, p2]):
            result = client.get_quote("AAPL")

        assert result.ticker == "AAPL"


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_returns_health_for_all_providers(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)

        mock_instance = MagicMock()
        mock_instance.health_check.return_value = _health()

        with patch.object(client._selector, "_instantiate", return_value=mock_instance):
            results = client.health_check()

        assert all(isinstance(v, HealthStatus) for v in results.values())

    def test_skips_providers_that_fail_to_instantiate(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)

        with patch.object(client._selector, "_instantiate", return_value=None):
            results = client.health_check()

        assert results == {}


# ---------------------------------------------------------------------------
# AsyncStockFeedClient
# ---------------------------------------------------------------------------

class TestAsyncClient:
    def test_get_ohlcv_returns_bars(self, tmp_db_path: str) -> None:
        client = _make_async_client(tmp_db_path)
        bars = [_bar()]

        async def _async_ohlcv(*a: object, **kw: object) -> list[OHLCVBar]:
            return bars

        mock_provider = MagicMock()
        mock_provider.async_get_ohlcv = _async_ohlcv

        async def _run() -> list[OHLCVBar]:
            with patch.object(client._selector, "select", return_value=[mock_provider]):
                return await client.get_ohlcv(
                    "AAPL",
                    Interval.ONE_DAY,
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 1, 31, tzinfo=timezone.utc),
                )

        result = asyncio.run(_run())
        assert result == bars

    def test_get_ohlcv_failover(self, tmp_db_path: str) -> None:
        client = _make_async_client(tmp_db_path)
        bars = [_bar()]

        async def _fail(*a: object, **kw: object) -> list[OHLCVBar]:
            raise ProviderUnavailableError("down", provider="p1")

        async def _succeed(*a: object, **kw: object) -> list[OHLCVBar]:
            return bars

        p1 = MagicMock()
        p1.async_get_ohlcv = _fail
        p2 = MagicMock()
        p2.async_get_ohlcv = _succeed

        async def _run() -> list[OHLCVBar]:
            with patch.object(client._selector, "select", return_value=[p1, p2]):
                return await client.get_ohlcv(
                    "AAPL",
                    Interval.ONE_DAY,
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 1, 31, tzinfo=timezone.utc),
                )

        result = asyncio.run(_run())
        assert result == bars

    def test_get_quote_returns_quote(self, tmp_db_path: str) -> None:
        client = _make_async_client(tmp_db_path)
        expected = _quote()

        async def _get_quote(ticker: str) -> Quote:
            return expected

        mock_provider = MagicMock()
        mock_provider.async_get_quote = _get_quote

        async def _run() -> Quote:
            with patch.object(client._selector, "select", return_value=[mock_provider]):
                return await client.get_quote("AAPL")

        result = asyncio.run(_run())
        assert result == expected

    def test_health_check_returns_dict(self, tmp_db_path: str) -> None:
        client = _make_async_client(tmp_db_path)
        status = _health()

        async def _async_health() -> HealthStatus:
            return status

        mock_instance = MagicMock()
        mock_instance.async_health_check = _async_health

        async def _run() -> dict[str, HealthStatus]:
            with patch.object(client._selector, "_instantiate", return_value=mock_instance):
                return await client.health_check()

        results = asyncio.run(_run())
        assert all(isinstance(v, HealthStatus) for v in results.values())
