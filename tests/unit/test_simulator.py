"""Unit tests for stockfeed.dev.simulator — simulate async generator."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stockfeed.dev.simulator import simulate
from stockfeed.exceptions import DevModeError
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar


def _make_bar(ticker: str, ts: datetime) -> OHLCVBar:
    return OHLCVBar(
        ticker=ticker,
        timestamp=ts,
        interval=Interval.ONE_DAY,
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("98"),
        close_raw=Decimal("102"),
        close_adj=Decimal("102"),
        volume=1_000_000,
        vwap=None,
        trade_count=None,
        provider="yfinance",
    )


def _make_client(bars: list[OHLCVBar], dev_mode: bool = True) -> MagicMock:
    client = MagicMock()
    client.settings = MagicMock()
    client.settings.dev_mode = dev_mode
    client.get_ohlcv = AsyncMock(return_value=bars)
    return client


_T1 = datetime(2024, 1, 2, tzinfo=timezone.utc)
_T2 = datetime(2024, 1, 3, tzinfo=timezone.utc)
_T3 = datetime(2024, 1, 4, tzinfo=timezone.utc)


class TestSimulate:
    async def test_yields_bars_in_order(self) -> None:
        bars = [_make_bar("AAPL", _T1), _make_bar("AAPL", _T2)]
        client = _make_client(bars)

        results = []
        async for bar in simulate("AAPL", _T1, _T3, Interval.ONE_DAY, speed=0, client=client):
            results.append(bar)

        assert [b.timestamp for b in results] == [_T1, _T2]

    async def test_sorts_bars_by_timestamp(self) -> None:
        # Bars returned out of order — simulator must sort them
        bars = [_make_bar("AAPL", _T2), _make_bar("AAPL", _T1)]
        client = _make_client(bars)

        results = []
        async for bar in simulate("AAPL", _T1, _T3, Interval.ONE_DAY, speed=0, client=client):
            results.append(bar)

        assert results[0].timestamp == _T1
        assert results[1].timestamp == _T2

    async def test_dev_mode_false_raises(self) -> None:
        client = _make_client([], dev_mode=False)

        with pytest.raises(DevModeError, match="dev_mode"):
            async for _ in simulate("AAPL", _T1, _T3, Interval.ONE_DAY, speed=0, client=client):
                pass

    async def test_speed_zero_skips_sleep(self) -> None:
        bars = [_make_bar("AAPL", _T1), _make_bar("AAPL", _T2)]
        client = _make_client(bars)

        with patch("stockfeed.dev.simulator.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            async for _ in simulate("AAPL", _T1, _T3, Interval.ONE_DAY, speed=0, client=client):
                pass

        mock_sleep.assert_not_called()

    async def test_speed_one_sleeps_interval_seconds(self) -> None:
        bars = [_make_bar("AAPL", _T1), _make_bar("AAPL", _T2)]
        client = _make_client(bars)
        sleep_calls: list[float] = []

        async def _fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with patch("stockfeed.dev.simulator.asyncio.sleep", side_effect=_fake_sleep):
            async for _ in simulate("AAPL", _T1, _T3, Interval.ONE_DAY, speed=1.0, client=client):
                pass

        # ONE_DAY = 86400s, speed=1 → sleep 86400 after each bar (except last)
        assert sleep_calls == pytest.approx([86400.0, 86400.0])

    async def test_speed_multiplier_divides_sleep(self) -> None:
        bars = [_make_bar("AAPL", _T1)]
        client = _make_client(bars)
        sleep_calls: list[float] = []

        async def _fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with patch("stockfeed.dev.simulator.asyncio.sleep", side_effect=_fake_sleep):
            async for _ in simulate("AAPL", _T1, _T2, Interval.ONE_DAY, speed=10.0, client=client):
                pass

        assert sleep_calls == pytest.approx([86400.0 / 10])

    async def test_accepts_string_dates(self) -> None:
        bars = [_make_bar("AAPL", _T1)]
        client = _make_client(bars)

        results = []
        async for bar in simulate("AAPL", "2024-01-02", "2024-01-04", "1d", speed=0, client=client):
            results.append(bar)

        assert len(results) == 1
        # Verify parsed dates were passed to get_ohlcv
        call_args = client.get_ohlcv.call_args[0]
        assert call_args[2].tzinfo is timezone.utc  # start
        assert call_args[3].tzinfo is timezone.utc  # end

    async def test_empty_bars_yields_nothing(self) -> None:
        client = _make_client([])

        results = []
        async for bar in simulate("AAPL", _T1, _T3, Interval.ONE_DAY, speed=0, client=client):
            results.append(bar)

        assert results == []

    async def test_string_interval_accepted(self) -> None:
        bars = [_make_bar("AAPL", _T1)]
        client = _make_client(bars)

        results = []
        async for bar in simulate("AAPL", _T1, _T2, "1d", speed=0, client=client):
            results.append(bar)

        assert len(results) == 1


class TestAsyncClientSimulate:
    async def test_client_simulate_raises_without_dev_mode(self, tmp_path) -> None:
        from stockfeed import AsyncStockFeedClient
        client = AsyncStockFeedClient(db_path=str(tmp_path / "c.db"))
        assert client.settings.dev_mode is False

        with pytest.raises(DevModeError):
            async for _ in client.simulate("AAPL", "2024-01-01", "2024-01-02", "1d", speed=0):
                pass

    async def test_client_dev_mode_kwarg(self, tmp_path) -> None:
        from stockfeed import AsyncStockFeedClient
        client = AsyncStockFeedClient(dev_mode=True, db_path=str(tmp_path / "c.db"))
        assert client.settings.dev_mode is True


class TestAsyncClientStreamQuote:
    async def test_stream_quote_method_exists(self, tmp_path) -> None:
        import inspect

        from stockfeed import AsyncStockFeedClient
        client = AsyncStockFeedClient(db_path=str(tmp_path / "c.db"))
        assert inspect.isasyncgenfunction(client.stream_quote)
