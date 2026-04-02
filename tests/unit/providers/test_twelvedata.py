"""Unit tests for TwelvedataNormalizer and TwelvedataProvider."""

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
from stockfeed.providers.twelvedata.normalizer import TwelvedataNormalizer
from stockfeed.providers.twelvedata.provider import TwelvedataProvider

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "providers" / "twelvedata"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# TwelvedataNormalizer tests (no HTTP)
# ---------------------------------------------------------------------------


class TestTwelvedataNormalizer:
    def setup_method(self) -> None:
        self.normalizer = TwelvedataNormalizer()

    def test_normalize_ohlcv_returns_bars(self) -> None:
        fixture = _load("ohlcv.json")
        data = fixture["data"]
        bars = self.normalizer.normalize_ohlcv((data, "AAPL", Interval.ONE_DAY))
        assert isinstance(bars, list)
        assert len(bars) == 2
        assert all(isinstance(b, OHLCVBar) for b in bars)
        assert bars[0].ticker == "AAPL"
        assert bars[0].provider == "twelvedata"

    def test_normalize_ohlcv_correct_values(self) -> None:
        fixture = _load("ohlcv.json")
        data = fixture["data"]
        bars = self.normalizer.normalize_ohlcv((data, "AAPL", Interval.ONE_DAY))
        first = bars[0]
        row = data["values"][0]
        assert first.open == Decimal(str(row["open"]))
        assert first.high == Decimal(str(row["high"]))
        assert first.low == Decimal(str(row["low"]))
        assert first.close_raw == Decimal(str(row["close"]))
        assert first.volume == int(row["volume"])

    def test_normalize_ohlcv_timestamps_are_utc(self) -> None:
        fixture = _load("ohlcv.json")
        data = fixture["data"]
        bars = self.normalizer.normalize_ohlcv((data, "AAPL", Interval.ONE_DAY))
        for bar in bars:
            assert bar.timestamp.tzinfo is not None
            assert bar.timestamp.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_normalize_ohlcv_sorted_ascending(self) -> None:
        fixture = _load("ohlcv.json")
        data = fixture["data"]
        bars = self.normalizer.normalize_ohlcv((data, "AAPL", Interval.ONE_DAY))
        timestamps = [b.timestamp for b in bars]
        assert timestamps == sorted(timestamps)

    def test_normalize_ohlcv_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            self.normalizer.normalize_ohlcv(({"values": [], "status": "ok"}, "AAPL", Interval.ONE_DAY))

    def test_normalize_quote_returns_quote(self) -> None:
        fixture = _load("quote.json")
        price_data = fixture["price_data"]
        quote_data = fixture["quote_data"]
        quote = self.normalizer.normalize_quote((price_data, quote_data, "AAPL"))
        assert quote.ticker == "AAPL"
        assert quote.last == Decimal(str(price_data["price"]))
        assert quote.open == Decimal(str(quote_data["open"]))
        assert quote.high == Decimal(str(quote_data["high"]))
        assert quote.low == Decimal(str(quote_data["low"]))
        assert quote.provider == "twelvedata"

    def test_normalize_ticker_info(self) -> None:
        fixture = _load("ticker_info.json")
        data = fixture["data"]
        info = self.normalizer.normalize_ticker_info((data, "AAPL"))
        assert info.ticker == "AAPL"
        assert info.name == "Apple Inc"
        assert info.exchange == "NASDAQ"
        assert info.currency == "USD"
        assert info.country == "United States"
        assert info.sector == "Technology"
        assert info.industry == "Consumer Electronics"
        assert info.provider == "twelvedata"

    def test_normalize_ticker_info_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            self.normalizer.normalize_ticker_info(({}, "AAPL"))


# ---------------------------------------------------------------------------
# TwelvedataProvider tests (mocked HTTP with respx)
# ---------------------------------------------------------------------------


class TestTwelvedataProvider:
    def setup_method(self) -> None:
        self.provider = TwelvedataProvider(api_key="test-key")
        self.ohlcv_fixture = _load("ohlcv.json")
        self.quote_fixture = _load("quote.json")
        self.info_fixture = _load("ticker_info.json")

    def test_provider_attributes(self) -> None:
        assert self.provider.name == "twelvedata"
        assert self.provider.requires_auth is True
        assert Interval.ONE_DAY in self.provider.supported_intervals

    def test_get_ohlcv(self) -> None:
        api_data = self.ohlcv_fixture["data"]
        with respx.mock:
            respx.get("https://api.twelvedata.com/time_series").mock(
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
        assert bars[0].provider == "twelvedata"

    def test_get_ohlcv_401_raises_auth_error(self) -> None:
        with respx.mock:
            respx.get("https://api.twelvedata.com/time_series").mock(
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
            respx.get("https://api.twelvedata.com/time_series").mock(
                return_value=httpx.Response(404)
            )
            with pytest.raises(TickerNotFoundError):
                self.provider.get_ohlcv(
                    "INVALID",
                    Interval.ONE_DAY,
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 1, 4, tzinfo=timezone.utc),
                )

    def test_get_ohlcv_error_status_raises_not_found(self) -> None:
        with respx.mock:
            respx.get("https://api.twelvedata.com/time_series").mock(
                return_value=httpx.Response(200, json={"status": "error", "message": "Symbol not found"})
            )
            with pytest.raises(TickerNotFoundError):
                self.provider.get_ohlcv(
                    "INVALID",
                    Interval.ONE_DAY,
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 1, 4, tzinfo=timezone.utc),
                )

    def test_get_quote(self) -> None:
        price_data = self.quote_fixture["price_data"]
        quote_data = self.quote_fixture["quote_data"]
        with respx.mock:
            respx.get("https://api.twelvedata.com/price").mock(
                return_value=httpx.Response(200, json=price_data)
            )
            respx.get("https://api.twelvedata.com/quote").mock(
                return_value=httpx.Response(200, json=quote_data)
            )
            quote = self.provider.get_quote("AAPL")
        assert quote.ticker == "AAPL"
        assert quote.provider == "twelvedata"
        assert isinstance(quote.last, Decimal)

    def test_get_ticker_info(self) -> None:
        api_data = self.info_fixture["data"]
        with respx.mock:
            respx.get("https://api.twelvedata.com/profile").mock(
                return_value=httpx.Response(200, json=api_data)
            )
            info = self.provider.get_ticker_info("AAPL")
        assert info.ticker == "AAPL"
        assert info.name == "Apple Inc"
        assert info.provider == "twelvedata"

    def test_health_check_healthy(self) -> None:
        price_data = self.quote_fixture["price_data"]
        with respx.mock:
            respx.get("https://api.twelvedata.com/price").mock(
                return_value=httpx.Response(200, json=price_data)
            )
            status = self.provider.health_check()
        assert status.provider == "twelvedata"
        assert status.healthy is True
        assert status.latency_ms is not None

    def test_health_check_unhealthy(self) -> None:
        with respx.mock:
            respx.get("https://api.twelvedata.com/price").mock(
                side_effect=httpx.ConnectError("connection refused")
            )
            status = self.provider.health_check()
        assert status.healthy is False
        assert status.error is not None
