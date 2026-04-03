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

        with (
            patch.object(client._selector, "select", return_value=[p1, p2]),
            pytest.raises(ProviderUnavailableError),
        ):
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

        with (
            patch.object(client._selector, "select", return_value=[p1, p2]),
            pytest.raises(ProviderAuthError),
        ):
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

        with (
            patch.object(client._selector, "select", return_value=[p1]),
            pytest.raises(TickerNotFoundError),
        ):
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


# ---------------------------------------------------------------------------
# get_ticker_info
# ---------------------------------------------------------------------------


class TestGetTickerInfo:
    def test_returns_ticker_info(self, tmp_db_path: str) -> None:
        from stockfeed.models.ticker import TickerInfo

        client = _make_client(tmp_db_path)
        expected = TickerInfo(
            ticker="AAPL",
            provider="yfinance",
            name="Apple Inc.",
            exchange="NASDAQ",
            currency="USD",
            sector=None,
            industry=None,
            market_cap=None,
            description=None,
            website=None,
            logo_url=None,
            phone=None,
            country=None,
        )

        mock_provider = MagicMock()
        mock_provider.get_ticker_info.return_value = expected

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            result = client.get_ticker_info("AAPL")

        assert result == expected

    def test_skips_not_implemented_provider(self, tmp_db_path: str) -> None:
        from stockfeed.models.ticker import TickerInfo

        client = _make_client(tmp_db_path)
        expected = TickerInfo(
            ticker="AAPL",
            provider="yfinance",
            name="Apple Inc.",
            exchange="NASDAQ",
            currency="USD",
            sector=None,
            industry=None,
            market_cap=None,
            description=None,
            website=None,
            logo_url=None,
            phone=None,
            country=None,
        )

        p1 = MagicMock()
        p1.get_ticker_info.side_effect = NotImplementedError("not supported")
        p2 = MagicMock()
        p2.get_ticker_info.return_value = expected

        with patch.object(client._selector, "select", return_value=[p1, p2]):
            result = client.get_ticker_info("AAPL")

        assert result == expected

    def test_raises_when_all_fail(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)

        p1 = MagicMock()
        p1.get_ticker_info.side_effect = ProviderUnavailableError("down", provider="p1")

        with (
            patch.object(client._selector, "select", return_value=[p1]),
            pytest.raises(ProviderUnavailableError),
        ):
            client.get_ticker_info("AAPL")


# ---------------------------------------------------------------------------
# AsyncStockFeedClient — additional coverage for get_ticker_info, health_check
# ---------------------------------------------------------------------------


class TestAsyncClientAdditional:
    def test_get_ticker_info_returns_info(self, tmp_db_path: str) -> None:
        from stockfeed.models.ticker import TickerInfo

        client = _make_async_client(tmp_db_path)
        expected = TickerInfo(
            ticker="AAPL",
            provider="yfinance",
            name="Apple",
            exchange="NASDAQ",
            currency="USD",
            sector=None,
            industry=None,
            market_cap=None,
            description=None,
            website=None,
            logo_url=None,
            phone=None,
            country=None,
        )

        async def _get_info(ticker: str) -> TickerInfo:
            return expected

        mock_provider = MagicMock()
        mock_provider.async_get_ticker_info = _get_info

        async def _run() -> TickerInfo:
            with patch.object(client._selector, "select", return_value=[mock_provider]):
                return await client.get_ticker_info("AAPL")

        assert asyncio.run(_run()) == expected

    def test_get_ticker_info_skips_not_implemented(self, tmp_db_path: str) -> None:
        from stockfeed.models.ticker import TickerInfo

        client = _make_async_client(tmp_db_path)
        expected = TickerInfo(
            ticker="AAPL",
            provider="yfinance",
            name="Apple",
            exchange="NASDAQ",
            currency="USD",
            sector=None,
            industry=None,
            market_cap=None,
            description=None,
            website=None,
            logo_url=None,
            phone=None,
            country=None,
        )

        async def _fail(ticker: str) -> TickerInfo:
            raise NotImplementedError("not supported")

        async def _ok(ticker: str) -> TickerInfo:
            return expected

        p1 = MagicMock()
        p1.async_get_ticker_info = _fail
        p2 = MagicMock()
        p2.async_get_ticker_info = _ok

        async def _run() -> TickerInfo:
            with patch.object(client._selector, "select", return_value=[p1, p2]):
                return await client.get_ticker_info("AAPL")

        assert asyncio.run(_run()) == expected

    def test_get_ticker_info_raises_when_all_fail(self, tmp_db_path: str) -> None:
        client = _make_async_client(tmp_db_path)

        async def _fail(ticker: str) -> None:
            raise ProviderUnavailableError("down", provider="p1")

        p1 = MagicMock()
        p1.async_get_ticker_info = _fail

        async def _run() -> None:
            with patch.object(client._selector, "select", return_value=[p1]):
                await client.get_ticker_info("AAPL")

        with pytest.raises(ProviderUnavailableError):
            asyncio.run(_run())

    def test_get_quote_all_fail_raises(self, tmp_db_path: str) -> None:
        client = _make_async_client(tmp_db_path)

        async def _fail(ticker: str) -> None:
            raise ProviderUnavailableError("down", provider="p1")

        p1 = MagicMock()
        p1.async_get_quote = _fail

        async def _run() -> None:
            with patch.object(client._selector, "select", return_value=[p1]):
                await client.get_quote("AAPL")

        with pytest.raises(ProviderUnavailableError):
            asyncio.run(_run())


class TestAsyncClientCacheHit:
    """Cover async_client get_ohlcv cache-hit path and ohlcv all-fail path."""

    def test_ohlcv_cache_hit_skips_provider(self, tmp_db_path: str) -> None:
        from datetime import timedelta

        client = _make_async_client(tmp_db_path)
        bars = [_bar()]

        # Pre-populate cache
        assert client._cache is not None
        client._cache.write(bars)

        mock_provider = MagicMock()

        async def _run() -> list[OHLCVBar]:
            with patch.object(client._selector, "select", return_value=[mock_provider]):
                return await client.get_ohlcv(
                    "AAPL", Interval.ONE_DAY, _TS, _TS + timedelta(days=1)
                )

        result = asyncio.run(_run())
        assert result == bars
        mock_provider.async_get_ohlcv.assert_not_called()

    def test_ohlcv_all_fail_raises(self, tmp_db_path: str) -> None:
        client = _make_async_client(tmp_db_path)

        async def _fail(*a, **kw):
            raise ProviderUnavailableError("down", provider="p1")

        p1 = MagicMock()
        p1.async_get_ohlcv = _fail

        async def _run() -> None:
            with patch.object(client._selector, "select", return_value=[p1]):
                await client.get_ohlcv(
                    "AAPL",
                    Interval.ONE_DAY,
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 1, 31, tzinfo=timezone.utc),
                )

        with pytest.raises(ProviderUnavailableError):
            asyncio.run(_run())


# ---------------------------------------------------------------------------
# Async tests using pytest-asyncio auto mode for better coverage tracking
# ---------------------------------------------------------------------------


async def test_async_ohlcv_failover_rate_limit_then_success(tmp_db_path: str) -> None:
    """Exercises lines 113-116 of async_client.py (rate-limit except branch)."""
    client = _make_async_client(tmp_db_path)
    bars = [_bar()]

    async def _fail(*a, **kw):
        raise ProviderRateLimitError("rate limited", provider="p1")

    async def _succeed(*a, **kw):
        return bars

    p1 = MagicMock()
    p1.async_get_ohlcv = _fail
    p2 = MagicMock()
    p2.async_get_ohlcv = _succeed

    with patch.object(client._selector, "select", return_value=[p1, p2]):
        result = await client.get_ohlcv(
            "AAPL",
            Interval.ONE_DAY,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 31, tzinfo=timezone.utc),
        )

    assert result == bars


async def test_async_ohlcv_all_fail(tmp_db_path: str) -> None:
    """All providers fail — exercises the raise in _ohlcv_with_failover."""
    client = _make_async_client(tmp_db_path)

    async def _fail(*a, **kw):
        raise ProviderUnavailableError("down", provider="p1")

    p1 = MagicMock()
    p1.async_get_ohlcv = _fail

    with (
        patch.object(client._selector, "select", return_value=[p1]),
        pytest.raises(ProviderUnavailableError),
    ):
        await client.get_ohlcv(
            "AAPL",
            Interval.ONE_DAY,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 31, tzinfo=timezone.utc),
        )


async def test_async_quote_all_fail(tmp_db_path: str) -> None:
    """All providers fail for quote — exercises get_quote raise."""
    client = _make_async_client(tmp_db_path)

    async def _fail(ticker: str):
        raise ProviderUnavailableError("down", provider="p1")

    p1 = MagicMock()
    p1.async_get_quote = _fail

    with (
        patch.object(client._selector, "select", return_value=[p1]),
        pytest.raises(ProviderUnavailableError),
    ):
        await client.get_quote("AAPL")


async def test_async_ticker_info_all_fail(tmp_db_path: str) -> None:
    """All providers fail for ticker info — exercises get_ticker_info raise."""
    client = _make_async_client(tmp_db_path)

    async def _fail(ticker: str):
        raise ProviderUnavailableError("down", provider="p1")

    p1 = MagicMock()
    p1.async_get_ticker_info = _fail

    with (
        patch.object(client._selector, "select", return_value=[p1]),
        pytest.raises(ProviderUnavailableError),
    ):
        await client.get_ticker_info("AAPL")


async def test_async_ohlcv_auth_error_propagates(tmp_db_path: str) -> None:
    """ProviderAuthError in async_get_ohlcv re-raises immediately (lines 114-115)."""
    client = _make_async_client(tmp_db_path)

    async def _fail(*a, **kw):
        raise ProviderAuthError("bad key", provider="p1")

    p1 = MagicMock()
    p1.async_get_ohlcv = _fail

    with (
        patch.object(client._selector, "select", return_value=[p1]),
        pytest.raises(ProviderAuthError),
    ):
        await client.get_ohlcv(
            "AAPL",
            Interval.ONE_DAY,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 31, tzinfo=timezone.utc),
        )


async def test_async_quote_auth_error_propagates(tmp_db_path: str) -> None:
    """ProviderAuthError in async_get_quote re-raises immediately (lines 140-141)."""
    client = _make_async_client(tmp_db_path)

    async def _fail(ticker: str):
        raise ProviderAuthError("bad key", provider="p1")

    p1 = MagicMock()
    p1.async_get_quote = _fail

    with (
        patch.object(client._selector, "select", return_value=[p1]),
        pytest.raises(ProviderAuthError),
    ):
        await client.get_quote("AAPL")


async def test_async_ticker_info_auth_error_propagates(tmp_db_path: str) -> None:
    """ProviderAuthError in async_get_ticker_info re-raises immediately (line 167)."""
    client = _make_async_client(tmp_db_path)

    async def _fail(ticker: str):
        raise ProviderAuthError("bad key", provider="p1")

    p1 = MagicMock()
    p1.async_get_ticker_info = _fail

    with (
        patch.object(client._selector, "select", return_value=[p1]),
        pytest.raises(ProviderAuthError),
    ):
        await client.get_ticker_info("AAPL")


class TestSyncClientAdditionalPaths:
    """Cover remaining missing branches in StockFeedClient."""

    def test_get_quote_auth_error_propagates(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        p1 = MagicMock()
        p1.get_quote.side_effect = ProviderAuthError("bad key", provider="p1")

        with (
            patch.object(client._selector, "select", return_value=[p1]),
            pytest.raises(ProviderAuthError),
        ):
            client.get_quote("AAPL")

    def test_get_quote_all_fail_raises(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        p1 = MagicMock()
        p1.get_quote.side_effect = ProviderUnavailableError("down", provider="p1")

        with (
            patch.object(client._selector, "select", return_value=[p1]),
            pytest.raises(ProviderUnavailableError),
        ):
            client.get_quote("AAPL")

    def test_get_ticker_info_auth_error_propagates(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        p1 = MagicMock()
        p1.get_ticker_info.side_effect = ProviderAuthError("bad key", provider="p1")

        with (
            patch.object(client._selector, "select", return_value=[p1]),
            pytest.raises(ProviderAuthError),
        ):
            client.get_ticker_info("AAPL")


class TestRateLimiterWindowExpiry:
    def test_expired_window_is_available(self, tmp_db_path: str) -> None:
        from stockfeed.providers.rate_limiter import RateLimiter

        rl = RateLimiter(db_path=tmp_db_path)
        # Set a window that has already expired (1 second window, started far in the past)
        from datetime import datetime, timedelta, timezone

        past = datetime.now(timezone.utc) - timedelta(seconds=120)
        conn = rl._conn
        conn.execute(
            """
            INSERT INTO rate_limit_state (provider, requests_made, window_start, window_seconds, limit_per_window, updated_at)
            VALUES ('tiingo', 10, ?, 60, 10, ?)
            ON CONFLICT (provider) DO UPDATE SET
                requests_made = 10, window_start = excluded.window_start,
                window_seconds = 60, limit_per_window = 10
        """,
            [past, past],
        )
        # Even though 10/10 requests used, window expired → should be available
        assert rl.is_available("tiingo") is True


class TestListProviders:
    def test_returns_all_providers(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        providers = client.list_providers()
        names = [p.name for p in providers]
        assert "yfinance" in names
        assert len(providers) >= 1

    def test_sorted_alphabetically(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        names = [p.name for p in client.list_providers()]
        assert names == sorted(names)

    def test_provider_info_fields(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        yf = next(p for p in client.list_providers() if p.name == "yfinance")
        assert yf.requires_auth is False
        assert len(yf.supported_intervals) > 0


class TestStringDatesAndIntervals:
    def test_get_ohlcv_with_string_dates(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        p1 = MagicMock()
        p1.get_ohlcv.return_value = [_bar("AAPL")]
        with patch.object(client._selector, "select", return_value=[p1]):
            bars = client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-31")
        assert len(bars) == 1
        p1.get_ohlcv.assert_called_once()
        _, _, start, end = p1.get_ohlcv.call_args[0]
        from datetime import timezone

        assert start.tzinfo is timezone.utc
        assert end.tzinfo is timezone.utc

    def test_get_ohlcv_with_string_interval(self, tmp_db_path: str) -> None:
        from stockfeed.models.interval import Interval

        client = _make_client(tmp_db_path)
        p1 = MagicMock()
        p1.get_ohlcv.return_value = [_bar("AAPL")]
        captured: list[Interval] = []

        def _select(ticker: str, interval: Interval, **kw):  # type: ignore[override]
            captured.append(interval)
            return [p1]

        with patch.object(client._selector, "select", side_effect=_select):
            bars = client.get_ohlcv("AAPL", "1h", "2024-01-01", "2024-01-31")
        assert len(bars) == 1
        assert captured[0] is Interval.ONE_HOUR

    def test_invalid_interval_string_raises(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        with pytest.raises(ValueError, match="Unknown interval"):
            client.get_ohlcv("AAPL", "2d", "2024-01-01", "2024-01-31")

    def test_invalid_date_string_raises(self, tmp_db_path: str) -> None:
        client = _make_client(tmp_db_path)
        with pytest.raises(ValueError, match="Cannot parse date"):
            client.get_ohlcv("AAPL", "1d", "not-a-date", "2024-01-31")
