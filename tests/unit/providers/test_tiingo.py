"""Unit tests for TiingoNormalizer and TiingoProvider."""

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
from stockfeed.providers.tiingo.normalizer import TiingoNormalizer
from stockfeed.providers.tiingo.provider import TiingoProvider

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "providers" / "tiingo"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# TiingoNormalizer tests (no HTTP)
# ---------------------------------------------------------------------------


class TestTiingoNormalizer:
    def setup_method(self) -> None:
        self.normalizer = TiingoNormalizer()

    def test_normalize_ohlcv_returns_bars(self) -> None:
        fixture = _load("ohlcv.json")
        rows = fixture["daily_rows"]
        bars = self.normalizer.normalize_ohlcv((rows, "AAPL", Interval.ONE_DAY))
        assert isinstance(bars, list)
        assert len(bars) == 2
        assert all(isinstance(b, OHLCVBar) for b in bars)
        assert bars[0].ticker == "AAPL"
        assert bars[0].provider == "tiingo"
        assert isinstance(bars[0].open, Decimal)
        assert isinstance(bars[0].close_raw, Decimal)

    def test_normalize_ohlcv_correct_values(self) -> None:
        fixture = _load("ohlcv.json")
        rows = fixture["daily_rows"]
        bars = self.normalizer.normalize_ohlcv((rows, "AAPL", Interval.ONE_DAY))
        first = bars[0]
        row = rows[0]
        assert first.open == Decimal(str(row["open"]))
        assert first.high == Decimal(str(row["high"]))
        assert first.low == Decimal(str(row["low"]))
        assert first.close_raw == Decimal(str(row["close"]))
        assert first.close_adj == Decimal(str(row["adjClose"]))
        assert first.volume == row["volume"]

    def test_normalize_ohlcv_timestamps_are_utc(self) -> None:
        fixture = _load("ohlcv.json")
        rows = fixture["daily_rows"]
        bars = self.normalizer.normalize_ohlcv((rows, "AAPL", Interval.ONE_DAY))
        for bar in bars:
            assert bar.timestamp.tzinfo is not None
            assert bar.timestamp.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_normalize_ohlcv_sorted_ascending(self) -> None:
        fixture = _load("ohlcv.json")
        rows = fixture["daily_rows"]
        bars = self.normalizer.normalize_ohlcv((rows, "AAPL", Interval.ONE_DAY))
        timestamps = [b.timestamp for b in bars]
        assert timestamps == sorted(timestamps)

    def test_normalize_ohlcv_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            self.normalizer.normalize_ohlcv(([], "AAPL", Interval.ONE_DAY))

    def test_normalize_quote_returns_quote(self) -> None:
        fixture = _load("quote.json")
        data = fixture["data"][0]
        quote = self.normalizer.normalize_quote((data, "AAPL"))
        assert quote.ticker == "AAPL"
        assert quote.last == Decimal(str(data["last"]))
        assert quote.bid == Decimal(str(data["bidPrice"]))
        assert quote.ask == Decimal(str(data["askPrice"]))
        assert quote.provider == "tiingo"

    def test_normalize_ticker_info(self) -> None:
        fixture = _load("ticker_info.json")
        data = fixture["data"]
        info = self.normalizer.normalize_ticker_info((data, "AAPL"))
        assert info.ticker == "AAPL"
        assert info.name == "Apple Inc"
        assert info.exchange == "NASDAQ"
        assert info.currency == "USD"
        assert info.provider == "tiingo"


# ---------------------------------------------------------------------------
# TiingoProvider tests (mocked HTTP with respx)
# ---------------------------------------------------------------------------


class TestTiingoProvider:
    def setup_method(self) -> None:
        self.provider = TiingoProvider(api_key="test-key")
        self.ohlcv_fixture = _load("ohlcv.json")
        self.quote_fixture = _load("quote.json")
        self.info_fixture = _load("ticker_info.json")

    def test_provider_attributes(self) -> None:
        assert self.provider.name == "tiingo"
        assert self.provider.requires_auth is True
        assert Interval.ONE_DAY in self.provider.supported_intervals

    def test_get_ohlcv(self) -> None:
        api_data = self.ohlcv_fixture["daily_rows"]
        with respx.mock:
            respx.get("https://api.tiingo.com/tiingo/daily/AAPL/prices").mock(
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
        assert bars[0].provider == "tiingo"
        assert isinstance(bars[0].close_raw, Decimal)

    def test_get_ohlcv_401_raises_auth_error(self) -> None:
        with respx.mock:
            respx.get("https://api.tiingo.com/tiingo/daily/AAPL/prices").mock(
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
            respx.get("https://api.tiingo.com/tiingo/daily/INVALID/prices").mock(
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
        api_data = self.quote_fixture["data"]
        with respx.mock:
            respx.get("https://api.tiingo.com/iex/AAPL").mock(
                return_value=httpx.Response(200, json=api_data)
            )
            quote = self.provider.get_quote("AAPL")
        assert quote.ticker == "AAPL"
        assert quote.provider == "tiingo"
        assert isinstance(quote.last, Decimal)

    def test_get_ticker_info(self) -> None:
        api_data = self.info_fixture["data"]
        with respx.mock:
            respx.get("https://api.tiingo.com/tiingo/daily/AAPL").mock(
                return_value=httpx.Response(200, json=api_data)
            )
            info = self.provider.get_ticker_info("AAPL")
        assert info.ticker == "AAPL"
        assert info.name == "Apple Inc"
        assert info.provider == "tiingo"

    def test_health_check_healthy(self) -> None:
        with respx.mock:
            respx.get("https://api.tiingo.com/api/test").mock(
                return_value=httpx.Response(
                    200, json={"message": "You successfully sent a request"}
                )
            )
            status = self.provider.health_check()
        assert status.provider == "tiingo"
        assert status.healthy is True
        assert status.latency_ms is not None

    def test_health_check_unhealthy(self) -> None:
        with respx.mock:
            respx.get("https://api.tiingo.com/api/test").mock(
                side_effect=httpx.ConnectError("connection refused")
            )
            status = self.provider.health_check()
        assert status.healthy is False
        assert status.error is not None


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


class TestTiingoNormalizerAdditional:
    def setup_method(self) -> None:
        from stockfeed.providers.tiingo.normalizer import TiingoNormalizer

        self.n = TiingoNormalizer()

    def test_normalize_ohlcv_invalid_raw_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_ohlcv("not_a_tuple")

    def test_normalize_ohlcv_empty_data_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_ohlcv(([], "AAPL", Interval.ONE_DAY))

    def test_normalize_quote_invalid_raw_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_quote("not_a_tuple")

    def test_normalize_quote_empty_data_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_quote(([], "AAPL"))

    def test_normalize_ticker_info_invalid_raw_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_ticker_info("not_a_tuple")

    def test_normalize_ticker_info_empty_data_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_ticker_info(({}, "AAPL"))

    def test_dec_none_returns_none(self) -> None:
        from stockfeed.providers.tiingo.normalizer import _dec

        assert _dec(None) is None

    def test_dec_invalid_returns_none(self) -> None:
        from stockfeed.providers.tiingo.normalizer import _dec

        assert _dec("not_a_number") is None

    def test_normalize_ticker_info_success(self) -> None:
        fixture = _load("ticker_info.json")
        info = self.n.normalize_ticker_info((fixture, "AAPL"))
        assert info.ticker == "AAPL"
        assert info.provider == "tiingo"
