"""E2E tests for AsyncStockFeedClient — all provider HTTP mocked via patch."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stockfeed.async_client import AsyncStockFeedClient
from stockfeed.config import StockFeedSettings
from stockfeed.exceptions import ProviderUnavailableError, TickerNotFoundError
from stockfeed.models.health import HealthStatus
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(tmp_path: object, *, dev_mode: bool = False) -> AsyncStockFeedClient:
    settings = StockFeedSettings(
        cache_path=str(tmp_path / "e2e_async.db"),  # type: ignore[operator]
        cache_enabled=True,
        log_level="WARNING",
    )
    return AsyncStockFeedClient(settings=settings, dev_mode=dev_mode)


def _make_bar(offset: int = 0, provider: str = "yfinance") -> OHLCVBar:
    return OHLCVBar(
        ticker="AAPL",
        timestamp=datetime(2024, 1, 1 + offset, tzinfo=timezone.utc),
        interval=Interval.ONE_DAY,
        open=Decimal("185"),
        high=Decimal("188"),
        low=Decimal("183"),
        close_raw=Decimal("187"),
        close_adj=Decimal("186"),
        volume=1_000_000,
        vwap=None,
        trade_count=None,
        provider=provider,
    )


def _make_quote() -> Quote:
    return Quote(
        ticker="AAPL",
        timestamp=datetime(2024, 1, 2, 15, 30, tzinfo=timezone.utc),
        bid=Decimal("186.90"),
        ask=Decimal("187.10"),
        bid_size=100,
        ask_size=200,
        last=Decimal("187.00"),
        last_size=50,
        volume=10_000_000,
        open=Decimal("185"),
        high=Decimal("188"),
        low=Decimal("184"),
        close=Decimal("186.50"),
        change=Decimal("0.50"),
        change_pct=Decimal("0.27"),
        provider="yfinance",
    )


def _make_ticker_info() -> TickerInfo:
    return TickerInfo(
        ticker="AAPL",
        name="Apple Inc.",
        exchange="NASDAQ",
        currency="USD",
        country="US",
        sector="Technology",
        industry="Consumer Electronics",
        market_cap=3_000_000_000_000,
        provider="yfinance",
    )


def _make_health(name: str = "yfinance") -> HealthStatus:
    return HealthStatus(
        provider=name,
        healthy=True,
        latency_ms=5.0,
        error=None,
        checked_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        rate_limit_remaining=None,
    )


def _mock_async_provider(name: str = "yfinance") -> MagicMock:
    """Return a MagicMock provider with async methods."""
    p = MagicMock()
    p.name = name
    p.async_get_ohlcv = AsyncMock()
    p.async_get_quote = AsyncMock()
    p.async_get_ticker_info = AsyncMock()
    p.async_health_check = AsyncMock()
    return p


# ---------------------------------------------------------------------------
# get_ohlcv
# ---------------------------------------------------------------------------


class TestAsyncClientGetOHLCV:
    async def test_get_ohlcv_returns_bars(self, tmp_path: object) -> None:
        client = _make_client(tmp_path)
        bars = [_make_bar(i) for i in range(5)]

        mock_provider = _mock_async_provider()
        mock_provider.async_get_ohlcv.return_value = bars

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            result = await client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-06")

        assert len(result) == 5
        assert all(isinstance(b, OHLCVBar) for b in result)

    async def test_get_ohlcv_accepts_interval_string(self, tmp_path: object) -> None:
        client = _make_client(tmp_path)
        bars = [_make_bar()]

        mock_provider = _mock_async_provider()
        mock_provider.async_get_ohlcv.return_value = bars

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            result = await client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-02")

        assert len(result) == 1

    async def test_get_ohlcv_second_call_hits_cache(self, tmp_path: object) -> None:
        client = _make_client(tmp_path)
        bars = [_make_bar(i) for i in range(3)]

        mock_provider = _mock_async_provider()
        mock_provider.async_get_ohlcv.return_value = bars

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            await client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-04")
            mock_provider.async_get_ohlcv.reset_mock()
            result = await client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-04")

        mock_provider.async_get_ohlcv.assert_not_called()
        assert len(result) == 3

    async def test_get_ohlcv_raises_on_all_failure(self, tmp_path: object) -> None:
        client = _make_client(tmp_path)

        mock_provider = _mock_async_provider()
        mock_provider.async_get_ohlcv.side_effect = ProviderUnavailableError("down", provider="p")

        with (
            patch.object(client._selector, "select", return_value=[mock_provider]),
            pytest.raises(ProviderUnavailableError),
        ):
            await client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-02")

    async def test_get_ohlcv_raises_ticker_not_found(self, tmp_path: object) -> None:
        client = _make_client(tmp_path)

        mock_provider = _mock_async_provider()
        mock_provider.async_get_ohlcv.side_effect = TickerNotFoundError(
            "No FAKE", provider="yfinance", ticker="FAKE"
        )

        with (
            patch.object(client._selector, "select", return_value=[mock_provider]),
            pytest.raises(TickerNotFoundError),
        ):
            await client.get_ohlcv("FAKE", "1d", "2024-01-01", "2024-01-02")


# ---------------------------------------------------------------------------
# get_quote
# ---------------------------------------------------------------------------


class TestAsyncClientGetQuote:
    async def test_get_quote_returns_quote(self, tmp_path: object) -> None:
        client = _make_client(tmp_path)
        quote = _make_quote()

        mock_provider = _mock_async_provider()
        mock_provider.async_get_quote.return_value = quote

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            result = await client.get_quote("AAPL")

        assert isinstance(result, Quote)
        assert result.last == Decimal("187.00")

    async def test_get_quote_raises_on_failure(self, tmp_path: object) -> None:
        client = _make_client(tmp_path)

        mock_provider = _mock_async_provider()
        mock_provider.async_get_quote.side_effect = ProviderUnavailableError("down", provider="p")

        with (
            patch.object(client._selector, "select", return_value=[mock_provider]),
            pytest.raises(ProviderUnavailableError),
        ):
            await client.get_quote("AAPL")


# ---------------------------------------------------------------------------
# get_ticker_info
# ---------------------------------------------------------------------------


class TestAsyncClientGetTickerInfo:
    async def test_get_ticker_info_returns_info(self, tmp_path: object) -> None:
        client = _make_client(tmp_path)
        info = _make_ticker_info()

        mock_provider = _mock_async_provider()
        mock_provider.async_get_ticker_info.return_value = info

        with patch.object(client._selector, "select", return_value=[mock_provider]):
            result = await client.get_ticker_info("AAPL")

        assert isinstance(result, TickerInfo)
        assert result.exchange == "NASDAQ"


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


class TestAsyncClientHealthCheck:
    async def test_health_check_returns_dict(self, tmp_path: object) -> None:
        client = _make_client(tmp_path)
        health = _make_health("yfinance")

        mock_provider = MagicMock()
        mock_provider.async_health_check = AsyncMock(return_value=health)

        with patch.object(client._selector, "_instantiate", return_value=mock_provider):
            result = await client.health_check()

        assert isinstance(result, dict)
        assert all(isinstance(v, HealthStatus) for v in result.values())

    async def test_health_check_single_provider(self, tmp_path: object) -> None:
        client = _make_client(tmp_path)
        health = _make_health("yfinance")

        mock_provider = MagicMock()
        mock_provider.async_health_check = AsyncMock(return_value=health)

        with patch.object(client._selector, "_instantiate", return_value=mock_provider):
            result = await client.health_check(provider="yfinance")

        assert "yfinance" in result


# ---------------------------------------------------------------------------
# dev_mode setting
# ---------------------------------------------------------------------------


class TestAsyncClientDevMode:
    async def test_dev_mode_kwarg_sets_settings(self, tmp_path: object) -> None:
        client = _make_client(tmp_path, dev_mode=True)
        assert client.settings.dev_mode is True

    async def test_dev_mode_false_by_default(self, tmp_path: object) -> None:
        client = _make_client(tmp_path)
        assert client.settings.dev_mode is False
