"""Unit tests for AlpacaNormalizer and AlpacaProvider."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from stockfeed.exceptions import ProviderAuthError, TickerNotFoundError, ValidationError
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.providers.alpaca.normalizer import AlpacaNormalizer
from stockfeed.providers.alpaca.provider import AlpacaProvider

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "providers" / "alpaca"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# AlpacaNormalizer tests (no HTTP)
# ---------------------------------------------------------------------------


class TestAlpacaNormalizer:
    def setup_method(self) -> None:
        self.normalizer = AlpacaNormalizer()

    def test_normalize_ohlcv_returns_bars(self) -> None:
        fixture = _load("ohlcv.json")
        bars_list = fixture["data"]["bars"]
        bars = self.normalizer.normalize_ohlcv((bars_list, "AAPL", Interval.ONE_DAY))
        assert isinstance(bars, list)
        assert len(bars) == 2
        assert all(isinstance(b, OHLCVBar) for b in bars)
        assert bars[0].ticker == "AAPL"
        assert bars[0].provider == "alpaca"

    def test_normalize_ohlcv_correct_values(self) -> None:
        fixture = _load("ohlcv.json")
        bars_list = fixture["data"]["bars"]
        bars = self.normalizer.normalize_ohlcv((bars_list, "AAPL", Interval.ONE_DAY))
        first = bars[0]
        row = bars_list[0]
        assert first.open == Decimal(str(row["o"]))
        assert first.high == Decimal(str(row["h"]))
        assert first.low == Decimal(str(row["l"]))
        assert first.close_raw == Decimal(str(row["c"]))
        assert first.volume == int(row["v"])
        assert first.vwap == Decimal(str(row["vw"]))
        assert first.trade_count == int(row["n"])

    def test_normalize_ohlcv_timestamps_are_utc(self) -> None:
        fixture = _load("ohlcv.json")
        bars_list = fixture["data"]["bars"]
        bars = self.normalizer.normalize_ohlcv((bars_list, "AAPL", Interval.ONE_DAY))
        for bar in bars:
            assert bar.timestamp.tzinfo is not None
            assert bar.timestamp.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_normalize_ohlcv_sorted_ascending(self) -> None:
        fixture = _load("ohlcv.json")
        bars_list = fixture["data"]["bars"]
        bars = self.normalizer.normalize_ohlcv((bars_list, "AAPL", Interval.ONE_DAY))
        timestamps = [b.timestamp for b in bars]
        assert timestamps == sorted(timestamps)

    def test_normalize_ohlcv_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            self.normalizer.normalize_ohlcv(([], "AAPL", Interval.ONE_DAY))

    def test_normalize_quote_returns_quote(self) -> None:
        fixture = _load("quote.json")
        quote_data = fixture["quote_data"]
        trade_data = fixture["trade_data"]
        quote = self.normalizer.normalize_quote((quote_data, trade_data, "AAPL"))
        assert quote.ticker == "AAPL"
        q = quote_data["quote"]
        t = trade_data["trade"]
        assert quote.last == Decimal(str(t["p"]))
        assert quote.bid == Decimal(str(q["bp"]))
        assert quote.ask == Decimal(str(q["ap"]))
        assert quote.provider == "alpaca"

    def test_normalize_ticker_info(self) -> None:
        fixture = _load("ticker_info.json")
        data = fixture["data"]
        info = self.normalizer.normalize_ticker_info((data, "AAPL"))
        assert info.ticker == "AAPL"
        assert info.name == "Apple Inc."
        assert info.exchange == "NASDAQ"
        assert info.currency == "USD"
        assert info.country == "US"
        assert info.provider == "alpaca"

    def test_normalize_ticker_info_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            self.normalizer.normalize_ticker_info(({}, "AAPL"))


# ---------------------------------------------------------------------------
# AlpacaProvider tests (mocked HTTP with respx)
# ---------------------------------------------------------------------------


class TestAlpacaProvider:
    def setup_method(self) -> None:
        self.provider = AlpacaProvider(api_key="test-key", secret_key="test-secret")
        self.ohlcv_fixture = _load("ohlcv.json")
        self.quote_fixture = _load("quote.json")
        self.info_fixture = _load("ticker_info.json")

    def test_provider_attributes(self) -> None:
        assert self.provider.name == "alpaca"
        assert self.provider.requires_auth is True
        assert Interval.ONE_DAY in self.provider.supported_intervals

    def test_get_ohlcv(self) -> None:
        api_data = self.ohlcv_fixture["data"]
        with respx.mock:
            respx.get("https://data.alpaca.markets/v2/stocks/AAPL/bars").mock(
                return_value=httpx.Response(200, json=api_data)
            )
            bars = self.provider.get_ohlcv(
                "AAPL",
                Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 4, tzinfo=timezone.utc),
            )
        assert len(bars) == 2
        assert bars[0].ticker == "AAPL"
        assert bars[0].provider == "alpaca"

    def test_get_ohlcv_401_raises_auth_error(self) -> None:
        with respx.mock:
            respx.get("https://data.alpaca.markets/v2/stocks/AAPL/bars").mock(
                return_value=httpx.Response(401)
            )
            with pytest.raises(ProviderAuthError):
                self.provider.get_ohlcv(
                    "AAPL",
                    Interval.ONE_DAY,
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 1, 4, tzinfo=timezone.utc),
                )

    def test_get_ohlcv_404_raises_not_found(self) -> None:
        with respx.mock:
            respx.get("https://data.alpaca.markets/v2/stocks/INVALID/bars").mock(
                return_value=httpx.Response(404)
            )
            with pytest.raises(TickerNotFoundError):
                self.provider.get_ohlcv(
                    "INVALID",
                    Interval.ONE_DAY,
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 1, 4, tzinfo=timezone.utc),
                )

    def test_get_quote(self) -> None:
        quote_data = self.quote_fixture["quote_data"]
        trade_data = self.quote_fixture["trade_data"]
        with respx.mock:
            respx.get("https://data.alpaca.markets/v2/stocks/AAPL/quotes/latest").mock(
                return_value=httpx.Response(200, json=quote_data)
            )
            respx.get("https://data.alpaca.markets/v2/stocks/AAPL/trades/latest").mock(
                return_value=httpx.Response(200, json=trade_data)
            )
            quote = self.provider.get_quote("AAPL")
        assert quote.ticker == "AAPL"
        assert quote.provider == "alpaca"
        assert isinstance(quote.last, Decimal)

    def test_get_ticker_info(self) -> None:
        api_data = self.info_fixture["data"]
        with respx.mock:
            respx.get("https://data.alpaca.markets/v2/assets/AAPL").mock(
                return_value=httpx.Response(200, json=api_data)
            )
            info = self.provider.get_ticker_info("AAPL")
        assert info.ticker == "AAPL"
        assert info.name == "Apple Inc."
        assert info.provider == "alpaca"

    def test_health_check_healthy(self) -> None:
        trade_data = self.quote_fixture["trade_data"]
        with respx.mock:
            respx.get("https://data.alpaca.markets/v2/stocks/AAPL/trades/latest").mock(
                return_value=httpx.Response(200, json=trade_data)
            )
            status = self.provider.health_check()
        assert status.provider == "alpaca"
        assert status.healthy is True
        assert status.latency_ms is not None

    def test_health_check_unhealthy(self) -> None:
        with respx.mock:
            respx.get("https://data.alpaca.markets/v2/stocks/AAPL/trades/latest").mock(
                side_effect=httpx.ConnectError("connection refused")
            )
            status = self.provider.health_check()
        assert status.healthy is False
        assert status.error is not None
