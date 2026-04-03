"""Unit tests for FinnhubNormalizer and FinnhubProvider."""

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
from stockfeed.providers.finnhub.normalizer import FinnhubNormalizer
from stockfeed.providers.finnhub.provider import FinnhubProvider

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "providers" / "finnhub"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# FinnhubNormalizer tests (no HTTP)
# ---------------------------------------------------------------------------


class TestFinnhubNormalizer:
    def setup_method(self) -> None:
        self.normalizer = FinnhubNormalizer()

    def test_normalize_ohlcv_returns_bars(self) -> None:
        fixture = _load("ohlcv.json")
        data = fixture["data"]
        bars = self.normalizer.normalize_ohlcv((data, "AAPL", Interval.ONE_DAY))
        assert isinstance(bars, list)
        assert len(bars) == 2
        assert all(isinstance(b, OHLCVBar) for b in bars)
        assert bars[0].ticker == "AAPL"
        assert bars[0].provider == "finnhub"

    def test_normalize_ohlcv_correct_values(self) -> None:
        fixture = _load("ohlcv.json")
        data = fixture["data"]
        bars = self.normalizer.normalize_ohlcv((data, "AAPL", Interval.ONE_DAY))
        first = bars[0]
        assert first.open == Decimal(str(data["o"][0]))
        assert first.high == Decimal(str(data["h"][0]))
        assert first.low == Decimal(str(data["l"][0]))
        assert first.close_raw == Decimal(str(data["c"][0]))
        assert first.volume == int(data["v"][0])
        assert first.close_adj is None  # Finnhub does not provide adjClose

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
            self.normalizer.normalize_ohlcv(({}, "AAPL", Interval.ONE_DAY))

    def test_normalize_quote_returns_quote(self) -> None:
        fixture = _load("quote.json")
        data = fixture["data"]
        quote = self.normalizer.normalize_quote((data, "AAPL"))
        assert quote.ticker == "AAPL"
        assert quote.last == Decimal(str(data["c"]))
        assert quote.open == Decimal(str(data["o"]))
        assert quote.high == Decimal(str(data["h"]))
        assert quote.low == Decimal(str(data["l"]))
        assert quote.close == Decimal(str(data["pc"]))
        assert quote.provider == "finnhub"

    def test_normalize_ticker_info(self) -> None:
        fixture = _load("ticker_info.json")
        data = fixture["data"]
        info = self.normalizer.normalize_ticker_info((data, "AAPL"))
        assert info.ticker == "AAPL"
        assert info.name == "Apple Inc"
        assert info.exchange == "NASDAQ/NMS (GLOBAL MARKET)"
        assert info.currency == "USD"
        assert info.country == "US"
        assert info.industry == "Technology"
        assert info.provider == "finnhub"

    def test_normalize_ticker_info_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            self.normalizer.normalize_ticker_info(({}, "AAPL"))


# ---------------------------------------------------------------------------
# FinnhubProvider tests (mocked HTTP with respx)
# ---------------------------------------------------------------------------


class TestFinnhubProvider:
    def setup_method(self) -> None:
        self.provider = FinnhubProvider(api_key="test-key")
        self.ohlcv_fixture = _load("ohlcv.json")
        self.quote_fixture = _load("quote.json")
        self.info_fixture = _load("ticker_info.json")

    def test_provider_attributes(self) -> None:
        assert self.provider.name == "finnhub"
        assert self.provider.requires_auth is True
        assert Interval.ONE_DAY in self.provider.supported_intervals

    def test_get_ohlcv(self) -> None:
        api_data = self.ohlcv_fixture["data"]
        with respx.mock:
            respx.get("https://finnhub.io/api/v1/stock/candles").mock(
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
        assert bars[0].provider == "finnhub"

    def test_get_ohlcv_no_data_raises_not_found(self) -> None:
        with respx.mock:
            respx.get("https://finnhub.io/api/v1/stock/candles").mock(
                return_value=httpx.Response(200, json={"s": "no_data"})
            )
            with pytest.raises(TickerNotFoundError):
                self.provider.get_ohlcv(
                    "INVALID",
                    Interval.ONE_DAY,
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 1, 4, tzinfo=timezone.utc),
                )

    def test_get_ohlcv_401_raises_auth_error(self) -> None:
        with respx.mock:
            respx.get("https://finnhub.io/api/v1/stock/candles").mock(
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
            respx.get("https://finnhub.io/api/v1/stock/candles").mock(
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
            respx.get("https://finnhub.io/api/v1/quote").mock(
                return_value=httpx.Response(200, json=api_data)
            )
            quote = self.provider.get_quote("AAPL")
        assert quote.ticker == "AAPL"
        assert quote.provider == "finnhub"
        assert isinstance(quote.last, Decimal)

    def test_get_ticker_info(self) -> None:
        api_data = self.info_fixture["data"]
        with respx.mock:
            respx.get("https://finnhub.io/api/v1/stock/profile2").mock(
                return_value=httpx.Response(200, json=api_data)
            )
            info = self.provider.get_ticker_info("AAPL")
        assert info.ticker == "AAPL"
        assert info.name == "Apple Inc"
        assert info.provider == "finnhub"

    def test_health_check_healthy(self) -> None:
        api_data = self.quote_fixture["data"]
        with respx.mock:
            respx.get("https://finnhub.io/api/v1/quote").mock(
                return_value=httpx.Response(200, json=api_data)
            )
            status = self.provider.health_check()
        assert status.provider == "finnhub"
        assert status.healthy is True
        assert status.latency_ms is not None

    def test_health_check_unhealthy(self) -> None:
        with respx.mock:
            respx.get("https://finnhub.io/api/v1/quote").mock(
                side_effect=httpx.ConnectError("connection refused")
            )
            status = self.provider.health_check()
        assert status.healthy is False
        assert status.error is not None


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


class TestFinnhubNormalizerAdditional:
    def setup_method(self) -> None:
        from stockfeed.providers.finnhub.normalizer import FinnhubNormalizer

        self.n = FinnhubNormalizer()

    def test_normalize_ohlcv_invalid_raw_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_ohlcv("not_a_tuple")

    def test_normalize_ohlcv_empty_data_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_ohlcv(({}, "AAPL", Interval.ONE_DAY))

    def test_normalize_quote_invalid_raw_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_quote("not_a_tuple")

    def test_normalize_quote_empty_data_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_quote(({}, "AAPL"))

    def test_normalize_ticker_info_invalid_raw_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_ticker_info("not_a_tuple")

    def test_normalize_ticker_info_empty_data_raises(self) -> None:
        from stockfeed.exceptions import ValidationError

        with pytest.raises(ValidationError):
            self.n.normalize_ticker_info(({}, "AAPL"))

    def test_dec_none_returns_none(self) -> None:
        from stockfeed.providers.finnhub.normalizer import _dec

        assert _dec(None) is None

    def test_dec_invalid_returns_none(self) -> None:
        from stockfeed.providers.finnhub.normalizer import _dec

        assert _dec("not_a_number") is None
