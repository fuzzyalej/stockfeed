"""Unit tests for YFinanceProvider and YFinanceNormalizer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stockfeed.exceptions import ProviderUnavailableError, TickerNotFoundError, ValidationError
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.providers.alpaca.provider import AlpacaProvider
from stockfeed.providers.coingecko.provider import CoingeckoProvider
from stockfeed.providers.finnhub.provider import FinnhubProvider
from stockfeed.providers.tiingo.provider import TiingoProvider
from stockfeed.providers.tradier.provider import TradierProvider
from stockfeed.providers.twelvedata.provider import TwelvedataProvider
from stockfeed.providers.yfinance.normalizer import YFinanceNormalizer
from stockfeed.providers.yfinance.provider import YFinanceProvider

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "providers" / "yfinance"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / name).read_text())


def _make_ohlcv_df(rows: list[dict]) -> pd.DataFrame:  # type: ignore[type-arg]
    """Build a yfinance-style OHLCV DataFrame from fixture rows."""
    records = [
        {
            "Open": r["open"],
            "High": r["high"],
            "Low": r["low"],
            "Close": r["close"],
            "Volume": r["volume"],
        }
        for r in rows
    ]
    index = pd.DatetimeIndex(
        [pd.Timestamp(r["timestamp"]) for r in rows],
        name="Date",
    )
    return pd.DataFrame(records, index=index)


def _make_adj_df(rows: list[dict]) -> pd.DataFrame:  # type: ignore[type-arg]
    records = [{"Close": r["close_adj"]} for r in rows]
    index = pd.DatetimeIndex(
        [pd.Timestamp(r["timestamp"]) for r in rows],
        name="Date",
    )
    return pd.DataFrame(records, index=index)


# ---------------------------------------------------------------------------
# YFinanceNormalizer tests
# ---------------------------------------------------------------------------


class TestYFinanceNormalizer:
    def setup_method(self) -> None:
        self.normalizer = YFinanceNormalizer()
        self.fixture = _load("ohlcv.json")
        self.rows = self.fixture["rows"]
        self.raw_df = _make_ohlcv_df(self.rows)
        self.adj_df = _make_adj_df(self.rows)

    def test_normalize_ohlcv_returns_list_of_ohlcv_bars(self) -> None:
        bars = self.normalizer.normalize_ohlcv((self.raw_df, self.adj_df, "AAPL", Interval.ONE_DAY))
        assert isinstance(bars, list)
        assert len(bars) == len(self.rows)
        assert all(isinstance(b, OHLCVBar) for b in bars)

    def test_normalize_ohlcv_correct_values(self) -> None:
        bars = self.normalizer.normalize_ohlcv((self.raw_df, self.adj_df, "AAPL", Interval.ONE_DAY))
        first = bars[0]
        row = self.rows[0]
        assert first.ticker == "AAPL"
        assert first.open == Decimal(str(row["open"]))
        assert first.close_raw == Decimal(str(row["close"]))
        assert first.close_adj == Decimal(str(row["close_adj"]))
        assert first.volume == row["volume"]
        assert first.provider == "yfinance"

    def test_normalize_ohlcv_timestamps_are_utc(self) -> None:
        bars = self.normalizer.normalize_ohlcv((self.raw_df, self.adj_df, "AAPL", Interval.ONE_DAY))
        for bar in bars:
            assert bar.timestamp.tzinfo is not None
            assert bar.timestamp.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_normalize_ohlcv_sorted_ascending(self) -> None:
        bars = self.normalizer.normalize_ohlcv((self.raw_df, self.adj_df, "AAPL", Interval.ONE_DAY))
        timestamps = [b.timestamp for b in bars]
        assert timestamps == sorted(timestamps)

    def test_normalize_ohlcv_empty_df_raises_validation_error(self) -> None:
        empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        with pytest.raises(ValidationError):
            self.normalizer.normalize_ohlcv((empty, empty, "AAPL", Interval.ONE_DAY))

    def test_normalize_ohlcv_bad_input_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            self.normalizer.normalize_ohlcv("not a tuple")

    def test_normalize_quote_returns_quote(self) -> None:
        fixture = _load("quote.json")
        quote = self.normalizer.normalize_quote((fixture["info"], "AAPL"))
        assert quote.ticker == "AAPL"
        assert quote.last == Decimal(str(fixture["info"]["currentPrice"]))
        assert quote.bid == Decimal(str(fixture["info"]["bid"]))
        assert quote.provider == "yfinance"

    def test_normalize_quote_empty_info_raises(self) -> None:
        with pytest.raises(ValidationError):
            self.normalizer.normalize_quote(({}, "AAPL"))

    def test_normalize_ticker_info_returns_ticker_info(self) -> None:
        fixture = _load("ticker_info.json")
        info = self.normalizer.normalize_ticker_info((fixture["info"], "AAPL"))
        assert info.ticker == "AAPL"
        assert info.name == "Apple Inc."
        assert info.sector == "Technology"
        assert info.market_cap == 2_900_000_000_000
        assert info.provider == "yfinance"

    def test_normalize_ticker_info_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            self.normalizer.normalize_ticker_info(({}, "AAPL"))

    def test_normalize_ohlcv_nan_volume_defaults_to_zero(self) -> None:
        """yfinance may return NaN for Volume on some bars; should default to 0."""
        import numpy as np

        df = pd.DataFrame(
            {
                "Open": [185.0],
                "High": [186.0],
                "Low": [184.0],
                "Close": [185.5],
                "Volume": [np.nan],
            },
            index=pd.DatetimeIndex([pd.Timestamp("2024-01-02", tz="UTC")]),
        )
        bars = self.normalizer.normalize_ohlcv((df, pd.DataFrame(), "AAPL", Interval.ONE_DAY))
        assert bars[0].volume == 0


# ---------------------------------------------------------------------------
# YFinanceProvider contract tests
# ---------------------------------------------------------------------------


class TestYFinanceProvider:
    def setup_method(self) -> None:
        self.provider = YFinanceProvider()
        self.ohlcv_fixture = _load("ohlcv.json")
        self.quote_fixture = _load("quote.json")
        self.info_fixture = _load("ticker_info.json")

    def _mock_ticker(self, rows: list[dict]) -> MagicMock:
        raw_df = _make_ohlcv_df(rows)
        adj_df = _make_adj_df(rows)
        mock_t = MagicMock()
        mock_t.history.side_effect = [raw_df, adj_df]
        mock_t.info = self.info_fixture["info"]
        mock_t.fast_info = {"regularMarketPrice": 188.32}
        return mock_t

    def test_provider_attributes(self) -> None:
        assert self.provider.name == "yfinance"
        assert self.provider.requires_auth is False
        assert Interval.ONE_DAY in self.provider.supported_intervals

    def test_get_ohlcv_returns_ohlcv_bars(self) -> None:
        rows = self.ohlcv_fixture["rows"]
        mock_t = self._mock_ticker(rows)
        with patch("stockfeed.providers.yfinance.provider.yf.Ticker", return_value=mock_t):
            bars = self.provider.get_ohlcv(
                "AAPL",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 9, tzinfo=timezone.utc),
            )
        assert len(bars) == len(rows)
        assert bars[0].ticker == "AAPL"
        assert bars[0].provider == "yfinance"
        assert isinstance(bars[0].close_raw, Decimal)

    def test_get_ohlcv_empty_raises_ticker_not_found(self) -> None:
        mock_t = MagicMock()
        empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        mock_t.history.return_value = empty
        with (
            patch("stockfeed.providers.yfinance.provider.yf.Ticker", return_value=mock_t),
            pytest.raises(TickerNotFoundError),
        ):
            self.provider.get_ohlcv(
                "INVALID",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 9, tzinfo=timezone.utc),
            )

    def test_get_ohlcv_exception_raises_provider_unavailable(self) -> None:
        mock_t = MagicMock()
        mock_t.history.side_effect = RuntimeError("network error")
        with (
            patch("stockfeed.providers.yfinance.provider.yf.Ticker", return_value=mock_t),
            pytest.raises(ProviderUnavailableError),
        ):
            self.provider.get_ohlcv(
                "AAPL",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 9, tzinfo=timezone.utc),
            )

    def test_get_quote_returns_quote(self) -> None:
        mock_t = MagicMock()
        mock_t.info = self.quote_fixture["info"]
        with patch("stockfeed.providers.yfinance.provider.yf.Ticker", return_value=mock_t):
            quote = self.provider.get_quote("AAPL")
        assert quote.ticker == "AAPL"
        assert quote.provider == "yfinance"

    def test_get_ticker_info_returns_ticker_info(self) -> None:
        mock_t = MagicMock()
        mock_t.info = self.info_fixture["info"]
        with patch("stockfeed.providers.yfinance.provider.yf.Ticker", return_value=mock_t):
            info = self.provider.get_ticker_info("AAPL")
        assert info.ticker == "AAPL"
        assert info.name == "Apple Inc."

    def test_health_check_returns_health_status(self) -> None:
        mock_t = MagicMock()
        mock_t.fast_info = {"regularMarketPrice": 188.32}
        with patch("stockfeed.providers.yfinance.provider.yf.Ticker", return_value=mock_t):
            status = self.provider.health_check()
        assert status.provider == "yfinance"
        assert status.healthy is True
        assert status.latency_ms is not None

    def test_health_check_on_exception_returns_unhealthy(self) -> None:
        from unittest.mock import PropertyMock

        mock_t = MagicMock()
        type(mock_t).fast_info = PropertyMock(side_effect=RuntimeError("down"))
        with patch("stockfeed.providers.yfinance.provider.yf.Ticker", return_value=mock_t):
            status = self.provider.health_check()
        assert status.healthy is False
        assert status.error is not None

    @pytest.mark.asyncio
    async def test_async_get_ohlcv_returns_bars(self) -> None:
        rows = self.ohlcv_fixture["rows"]
        mock_t = self._mock_ticker(rows)
        with patch("stockfeed.providers.yfinance.provider.yf.Ticker", return_value=mock_t):
            bars = await self.provider.async_get_ohlcv(
                "AAPL",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 9, tzinfo=timezone.utc),
            )
        assert len(bars) == len(rows)


# ---------------------------------------------------------------------------
# Provider contract: parametrised check all providers instantiate
# ---------------------------------------------------------------------------

ALL_PROVIDERS = [
    YFinanceProvider,
    TiingoProvider,
    FinnhubProvider,
    TwelvedataProvider,
    AlpacaProvider,
    TradierProvider,
    CoingeckoProvider,
]


@pytest.mark.parametrize("provider_class", ALL_PROVIDERS)
def test_provider_contract_instantiates(provider_class: type) -> None:
    """Every provider must instantiate without error."""
    p = provider_class()
    assert isinstance(p.name, str)
    assert isinstance(p.supported_intervals, list)
    assert isinstance(p.requires_auth, bool)


# Only providers that are still stubs (not yet implemented)
_STUB_PROVIDERS = [CoingeckoProvider]


@pytest.mark.parametrize("provider_class", _STUB_PROVIDERS)
def test_stub_providers_raise_not_implemented(provider_class: type) -> None:
    """Stub providers must raise NotImplementedError (not crash) on method calls."""
    p = provider_class()
    with pytest.raises(NotImplementedError):
        p.get_ohlcv(
            "AAPL",
            Interval.ONE_DAY,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 9, tzinfo=timezone.utc),
        )


# ---------------------------------------------------------------------------
# Async method coverage
# ---------------------------------------------------------------------------


class TestYFinanceProviderAsync:
    """Async wrappers just call to_thread — smoke-test that they run."""

    def test_async_get_ohlcv_delegates_to_sync(self) -> None:
        import asyncio
        from datetime import datetime, timezone
        from unittest.mock import patch

        from stockfeed.models.interval import Interval
        from stockfeed.providers.yfinance.provider import YFinanceProvider

        p = YFinanceProvider()
        bars = []  # empty but valid list

        async def _run():
            with patch.object(p, "get_ohlcv", return_value=bars):
                result = await p.async_get_ohlcv(
                    "AAPL",
                    Interval.ONE_DAY,
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 1, 31, tzinfo=timezone.utc),
                )
            return result

        result = asyncio.run(_run())
        assert result == bars

    def test_async_get_quote_delegates_to_sync(self) -> None:
        import asyncio
        from unittest.mock import MagicMock, patch

        from stockfeed.providers.yfinance.provider import YFinanceProvider

        p = YFinanceProvider()
        mock_quote = MagicMock()

        async def _run():
            with patch.object(p, "get_quote", return_value=mock_quote):
                return await p.async_get_quote("AAPL")

        assert asyncio.run(_run()) is mock_quote

    def test_async_get_ticker_info_delegates_to_sync(self) -> None:
        import asyncio
        from unittest.mock import MagicMock, patch

        from stockfeed.providers.yfinance.provider import YFinanceProvider

        p = YFinanceProvider()
        mock_info = MagicMock()

        async def _run():
            with patch.object(p, "get_ticker_info", return_value=mock_info):
                return await p.async_get_ticker_info("AAPL")

        assert asyncio.run(_run()) is mock_info

    def test_async_health_check_delegates_to_sync(self) -> None:
        import asyncio
        from unittest.mock import MagicMock, patch

        from stockfeed.providers.yfinance.provider import YFinanceProvider

        p = YFinanceProvider()
        mock_status = MagicMock()

        async def _run():
            with patch.object(p, "health_check", return_value=mock_status):
                return await p.async_health_check()

        assert asyncio.run(_run()) is mock_status
