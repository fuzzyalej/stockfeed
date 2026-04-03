"""Unit tests for TradierNormalizer and TradierProvider."""

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
from stockfeed.providers.tradier.normalizer import TradierNormalizer
from stockfeed.providers.tradier.provider import TradierProvider

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "providers" / "tradier"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# TradierNormalizer tests (no HTTP)
# ---------------------------------------------------------------------------


class TestTradierNormalizer:
    def setup_method(self) -> None:
        self.normalizer = TradierNormalizer()

    def test_normalize_ohlcv_returns_bars(self) -> None:
        fixture = _load("ohlcv.json")
        data = fixture["daily_data"]
        bars = self.normalizer.normalize_ohlcv((data, "AAPL", Interval.ONE_DAY, False))
        assert isinstance(bars, list)
        assert len(bars) == 2
        assert all(isinstance(b, OHLCVBar) for b in bars)
        assert bars[0].ticker == "AAPL"
        assert bars[0].provider == "tradier"

    def test_normalize_ohlcv_correct_values(self) -> None:
        fixture = _load("ohlcv.json")
        data = fixture["daily_data"]
        bars = self.normalizer.normalize_ohlcv((data, "AAPL", Interval.ONE_DAY, False))
        first = bars[0]
        row = data["history"]["day"][0]
        assert first.open == Decimal(str(row["open"]))
        assert first.high == Decimal(str(row["high"]))
        assert first.low == Decimal(str(row["low"]))
        assert first.close_raw == Decimal(str(row["close"]))
        assert first.volume == int(row["volume"])

    def test_normalize_ohlcv_timestamps_are_utc(self) -> None:
        fixture = _load("ohlcv.json")
        data = fixture["daily_data"]
        bars = self.normalizer.normalize_ohlcv((data, "AAPL", Interval.ONE_DAY, False))
        for bar in bars:
            assert bar.timestamp.tzinfo is not None
            assert bar.timestamp.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_normalize_ohlcv_sorted_ascending(self) -> None:
        fixture = _load("ohlcv.json")
        data = fixture["daily_data"]
        bars = self.normalizer.normalize_ohlcv((data, "AAPL", Interval.ONE_DAY, False))
        timestamps = [b.timestamp for b in bars]
        assert timestamps == sorted(timestamps)

    def test_normalize_ohlcv_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            self.normalizer.normalize_ohlcv(({}, "AAPL", Interval.ONE_DAY, False))

    def test_normalize_quote_returns_quote(self) -> None:
        fixture = _load("quote.json")
        data = fixture["data"]
        quote = self.normalizer.normalize_quote((data, "AAPL"))
        assert quote.ticker == "AAPL"
        q = data["quotes"]["quote"]
        assert quote.last == Decimal(str(q["last"]))
        assert quote.bid == Decimal(str(q["bid"]))
        assert quote.ask == Decimal(str(q["ask"]))
        assert quote.provider == "tradier"

    def test_normalize_quote_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            self.normalizer.normalize_quote(({}, "AAPL"))

    def test_normalize_ticker_info_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            self.normalizer.normalize_ticker_info(({}, "AAPL"))


# ---------------------------------------------------------------------------
# TradierProvider tests (mocked HTTP with respx)
# ---------------------------------------------------------------------------


class TestTradierProvider:
    def setup_method(self) -> None:
        self.provider = TradierProvider(api_key="test-key")
        self.ohlcv_fixture = _load("ohlcv.json")
        self.quote_fixture = _load("quote.json")

    def test_provider_attributes(self) -> None:
        assert self.provider.name == "tradier"
        assert self.provider.requires_auth is True
        assert Interval.ONE_DAY in self.provider.supported_intervals

    def test_get_ohlcv(self) -> None:
        api_data = self.ohlcv_fixture["daily_data"]
        with respx.mock:
            respx.get("https://api.tradier.com/v1/markets/history").mock(
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
        assert bars[0].provider == "tradier"

    def test_get_ohlcv_401_raises_auth_error(self) -> None:
        with respx.mock:
            respx.get("https://api.tradier.com/v1/markets/history").mock(
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
            respx.get("https://api.tradier.com/v1/markets/history").mock(
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
            respx.get("https://api.tradier.com/v1/markets/quotes").mock(
                return_value=httpx.Response(200, json=api_data)
            )
            quote = self.provider.get_quote("AAPL")
        assert quote.ticker == "AAPL"
        assert quote.provider == "tradier"
        assert isinstance(quote.last, Decimal)

    def test_get_ticker_info_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            self.provider.get_ticker_info("AAPL")

    def test_health_check_healthy(self) -> None:
        with respx.mock:
            respx.get("https://api.tradier.com/v1/markets/clock").mock(
                return_value=httpx.Response(200, json={"clock": {"state": "closed"}})
            )
            status = self.provider.health_check()
        assert status.provider == "tradier"
        assert status.healthy is True
        assert status.latency_ms is not None

    def test_health_check_unhealthy(self) -> None:
        with respx.mock:
            respx.get("https://api.tradier.com/v1/markets/clock").mock(
                side_effect=httpx.ConnectError("connection refused")
            )
            status = self.provider.health_check()
        assert status.healthy is False
        assert status.error is not None


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


class TestTradierNormalizerAdditional:
    def setup_method(self) -> None:
        self.n = TradierNormalizer()

    def test_normalize_ohlcv_invalid_raw_raises(self) -> None:
        from stockfeed.exceptions import ValidationError
        with pytest.raises(ValidationError):
            self.n.normalize_ohlcv("not_a_tuple")

    def test_normalize_ohlcv_empty_data_raises(self) -> None:
        from stockfeed.exceptions import ValidationError
        with pytest.raises(ValidationError):
            self.n.normalize_ohlcv((None, "AAPL", Interval.ONE_DAY, False))

    def test_normalize_ohlcv_intraday(self) -> None:
        row = {"time": "2024-01-02 09:30:00", "open": "185", "high": "186",
               "low": "184", "close": "185.5", "volume": "1000"}
        data = {"series": {"data": [row]}}
        bars = self.n.normalize_ohlcv((data, "AAPL", Interval.ONE_MINUTE, True))
        assert len(bars) >= 1
        assert bars[0].interval == Interval.ONE_MINUTE

    def test_normalize_ohlcv_intraday_single_row_dict(self) -> None:
        """Tradier sometimes returns a single row as a dict instead of list."""
        row = {"time": "2024-01-02 09:30:00", "open": "185", "high": "186",
               "low": "184", "close": "185.5", "volume": "1000"}
        data = {"series": {"data": row}}
        bars = self.n.normalize_ohlcv((data, "AAPL", Interval.ONE_MINUTE, True))
        assert len(bars) == 1

    def test_normalize_ohlcv_empty_intraday_raises(self) -> None:
        from stockfeed.exceptions import ValidationError
        data = {"series": {"data": []}}
        with pytest.raises(ValidationError):
            self.n.normalize_ohlcv((data, "AAPL", Interval.ONE_MINUTE, True))

    def test_normalize_ohlcv_daily_single_row_dict(self) -> None:
        """Tradier may return single daily row as dict."""
        row = {"date": "2024-01-02", "open": "185", "high": "186",
               "low": "184", "close": "185.5", "volume": "1000"}
        data = {"history": {"day": row}}
        bars = self.n.normalize_ohlcv((data, "AAPL", Interval.ONE_DAY, False))
        assert len(bars) == 1

    def test_normalize_quote_invalid_raw_raises(self) -> None:
        from stockfeed.exceptions import ValidationError
        with pytest.raises(ValidationError):
            self.n.normalize_quote("not_a_tuple")

    def test_normalize_quote_empty_data_raises(self) -> None:
        from stockfeed.exceptions import ValidationError
        with pytest.raises(ValidationError):
            self.n.normalize_quote((None, "AAPL"))

    def test_normalize_ticker_info_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            self.n.normalize_ticker_info(("data", "AAPL"))

    def test_dec_none_returns_none(self) -> None:
        from stockfeed.providers.tradier.normalizer import _dec
        assert _dec(None) is None

    def test_dec_invalid_returns_none(self) -> None:
        from stockfeed.providers.tradier.normalizer import _dec
        assert _dec("not_a_number") is None

    def test_parse_dt_iso_format(self) -> None:
        from datetime import timezone

        from stockfeed.providers.tradier.normalizer import _parse_dt
        dt = _parse_dt("2024-01-02T09:30:00")
        assert dt.tzinfo == timezone.utc

    def test_parse_dt_space_format(self) -> None:
        from stockfeed.providers.tradier.normalizer import _parse_dt
        dt = _parse_dt("2024-01-02 09:30:00")
        assert dt.year == 2024

    def test_parse_dt_with_z_suffix(self) -> None:
        from datetime import timezone

        from stockfeed.providers.tradier.normalizer import _parse_dt
        dt = _parse_dt("2024-01-02T09:30:00Z")
        assert dt.tzinfo == timezone.utc
        assert dt.year == 2024

    def test_parse_dt_iso_with_offset(self) -> None:
        from datetime import timezone

        from stockfeed.providers.tradier.normalizer import _parse_dt
        dt = _parse_dt("2024-01-02T09:30:00+00:00")
        assert dt.tzinfo == timezone.utc
