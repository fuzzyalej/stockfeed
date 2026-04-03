"""E2E tests for SSE quote streaming and dev simulator."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from stockfeed.async_client import AsyncStockFeedClient
from stockfeed.config import StockFeedSettings
from stockfeed.exceptions import (
    DevModeError,
    ProviderAuthError,
    ProviderUnavailableError,
    TickerNotFoundError,
)
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(tmp_path: object, *, dev_mode: bool = False) -> AsyncStockFeedClient:
    settings = StockFeedSettings(
        cache_path=str(tmp_path / "streaming.db"),  # type: ignore[operator]
        cache_enabled=True,
        dev_mode=dev_mode,
        log_level="WARNING",
    )
    return AsyncStockFeedClient(settings=settings)


def _make_quote(last: str = "187.00") -> Quote:
    return Quote(
        ticker="AAPL",
        timestamp=datetime(2024, 1, 2, 15, 30, tzinfo=timezone.utc),
        bid=Decimal("186.90"),
        ask=Decimal("187.10"),
        bid_size=100,
        ask_size=200,
        last=Decimal(last),
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


def _make_bar(offset: int = 0) -> OHLCVBar:
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
        provider="yfinance",
    )


# ---------------------------------------------------------------------------
# SSE stream_quote E2E
# ---------------------------------------------------------------------------


class TestStreamQuoteE2E:
    async def test_stream_yields_quotes_via_client(self, tmp_path: object) -> None:
        """client.stream_quote() yields Quote objects from get_quote()."""
        client = _make_client(tmp_path)
        quotes = [_make_quote(f"18{i}.00") for i in range(3)]
        call_count = 0

        async def fake_get_quote(ticker: str, provider: str | None = None) -> Quote:
            nonlocal call_count
            q = quotes[call_count]
            call_count += 1
            return q

        with patch.object(client, "get_quote", side_effect=fake_get_quote):
            with patch("asyncio.sleep", new=AsyncMock()):
                collected = []
                async for q in client.stream_quote("AAPL", interval=0.001):
                    collected.append(q)
                    if len(collected) >= 3:
                        break

        assert len(collected) == 3
        assert all(isinstance(q, Quote) for q in collected)

    async def test_stream_propagates_auth_error(self, tmp_path: object) -> None:
        """ProviderAuthError terminates the stream immediately."""
        client = _make_client(tmp_path)

        async def fail_auth(ticker: str, provider: str | None = None) -> Quote:
            raise ProviderAuthError("bad key", provider="yfinance")

        with patch.object(client, "get_quote", side_effect=fail_auth):
            with pytest.raises(ProviderAuthError):
                async for _ in client.stream_quote("AAPL"):
                    pass

    async def test_stream_propagates_ticker_not_found(self, tmp_path: object) -> None:
        """TickerNotFoundError terminates the stream immediately."""
        client = _make_client(tmp_path)

        async def fail_not_found(ticker: str, provider: str | None = None) -> Quote:
            raise TickerNotFoundError("no such ticker", ticker="FAKE", provider="yfinance")

        with patch.object(client, "get_quote", side_effect=fail_not_found):
            with pytest.raises(TickerNotFoundError):
                async for _ in client.stream_quote("FAKE"):
                    pass

    async def test_stream_retries_on_transient_error(self, tmp_path: object) -> None:
        """A single ProviderUnavailableError is retried; the next successful call yields."""
        client = _make_client(tmp_path)
        good_quote = _make_quote()
        calls = [
            ProviderUnavailableError("blip", provider="yfinance"),
            good_quote,
        ]
        idx = 0

        async def flaky(ticker: str, provider: str | None = None) -> Quote:
            nonlocal idx
            result = calls[idx]
            idx += 1
            if isinstance(result, Exception):
                raise result
            return result  # type: ignore[return-value]

        with patch.object(client, "get_quote", side_effect=flaky):
            with patch("asyncio.sleep", new=AsyncMock()):
                collected = []
                async for q in client.stream_quote("AAPL", max_errors=5):
                    collected.append(q)
                    if len(collected) >= 1:
                        break

        assert len(collected) == 1
        assert isinstance(collected[0], Quote)

    async def test_stream_raises_after_max_errors(self, tmp_path: object) -> None:
        """After max_errors consecutive failures, the stream raises."""
        client = _make_client(tmp_path)

        async def always_fail(ticker: str, provider: str | None = None) -> Quote:
            raise ProviderUnavailableError("down", provider="yfinance")

        with patch.object(client, "get_quote", side_effect=always_fail):
            with patch("asyncio.sleep", new=AsyncMock()):
                with pytest.raises(ProviderUnavailableError):
                    async for _ in client.stream_quote("AAPL", max_errors=3):
                        pass


# ---------------------------------------------------------------------------
# Dev simulator E2E
# ---------------------------------------------------------------------------


class TestSimulatorE2E:
    async def test_simulate_yields_bars_in_order(self, tmp_path: object) -> None:
        """client.simulate() yields bars sorted by timestamp."""
        client = _make_client(tmp_path, dev_mode=True)
        bars = [_make_bar(i) for i in range(5)]

        with patch.object(client, "get_ohlcv", new=AsyncMock(return_value=bars)):
            with patch("asyncio.sleep", new=AsyncMock()):
                collected = []
                async for bar in client.simulate("AAPL", "2024-01-01", "2024-01-06", "1d", speed=0):
                    collected.append(bar)

        assert len(collected) == 5
        timestamps = [b.timestamp for b in collected]
        assert timestamps == sorted(timestamps)

    async def test_simulate_raises_dev_mode_error_when_disabled(
        self, tmp_path: object
    ) -> None:
        """simulate() raises DevModeError when dev_mode is False."""
        client = _make_client(tmp_path, dev_mode=False)

        with pytest.raises(DevModeError):
            async for _ in client.simulate("AAPL", "2024-01-01", "2024-01-06", "1d"):
                pass

    async def test_simulate_speed_zero_skips_sleep(self, tmp_path: object) -> None:
        """speed=0 must not call asyncio.sleep."""
        client = _make_client(tmp_path, dev_mode=True)
        bars = [_make_bar(i) for i in range(3)]

        with patch.object(client, "get_ohlcv", new=AsyncMock(return_value=bars)):
            with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
                async for _ in client.simulate("AAPL", "2024-01-01", "2024-01-04", "1d", speed=0):
                    pass

        mock_sleep.assert_not_called()

    async def test_simulate_accepts_string_dates(self, tmp_path: object) -> None:
        """simulate() coerces string dates the same as get_ohlcv."""
        client = _make_client(tmp_path, dev_mode=True)
        bars = [_make_bar()]

        with patch.object(client, "get_ohlcv", new=AsyncMock(return_value=bars)):
            with patch("asyncio.sleep", new=AsyncMock()):
                collected = []
                async for bar in client.simulate("AAPL", "2024-01-01", "2024-01-02", "1d", speed=0):
                    collected.append(bar)

        assert len(collected) == 1

    async def test_simulate_bar_count(self, tmp_path: object) -> None:
        """simulate yields exactly as many bars as get_ohlcv returns."""
        client = _make_client(tmp_path, dev_mode=True)
        bars = [_make_bar(i) for i in range(10)]

        with patch.object(client, "get_ohlcv", new=AsyncMock(return_value=bars)):
            with patch("asyncio.sleep", new=AsyncMock()):
                collected = []
                async for bar in client.simulate(
                    "AAPL", "2024-01-01", "2024-01-11", "1d", speed=0
                ):
                    collected.append(bar)

        assert len(collected) == 10
