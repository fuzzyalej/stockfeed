"""Unit tests for all Pydantic models."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from stockfeed.models import Interval, OHLCVBar, Quote, StockFeedResponse, TickerInfo


def make_ohlcv(**kwargs):  # type: ignore[no-untyped-def]
    defaults = dict(
        ticker="AAPL",
        timestamp=datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
        interval=Interval.ONE_DAY,
        open=Decimal("185.00"),
        high=Decimal("186.50"),
        low=Decimal("184.20"),
        close_raw=Decimal("185.90"),
        close_adj=Decimal("185.90"),
        volume=55_000_000,
        vwap=None,
        trade_count=None,
        provider="yfinance",
    )
    defaults.update(kwargs)
    return OHLCVBar(**defaults)


class TestInterval:
    def test_values(self) -> None:
        assert Interval.ONE_DAY == "1d"
        assert Interval.ONE_MINUTE == "1m"
        assert Interval.ONE_MONTH == "1mo"

    def test_from_string(self) -> None:
        assert Interval("1h") == Interval.ONE_HOUR

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            Interval("invalid")


class TestOHLCVBar:
    def test_valid(self) -> None:
        bar = make_ohlcv()
        assert bar.ticker == "AAPL"
        assert bar.interval == Interval.ONE_DAY

    def test_ticker_normalised_to_upper(self) -> None:
        bar = make_ohlcv(ticker="aapl")
        assert bar.ticker == "AAPL"

    def test_empty_ticker_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            make_ohlcv(ticker="   ")

    def test_optional_fields_none(self) -> None:
        bar = make_ohlcv(close_adj=None, vwap=None, trade_count=None)
        assert bar.close_adj is None
        assert bar.vwap is None
        assert bar.trade_count is None


class TestQuote:
    def test_valid(self) -> None:
        q = Quote(
            ticker="MSFT",
            timestamp=datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
            bid=Decimal("374.90"),
            ask=Decimal("375.10"),
            bid_size=100,
            ask_size=200,
            last=Decimal("375.00"),
            last_size=50,
            volume=20_000_000,
            open=Decimal("372.00"),
            high=Decimal("376.00"),
            low=Decimal("371.50"),
            close=Decimal("373.80"),
            change=Decimal("1.20"),
            change_pct=Decimal("0.32"),
            provider="yfinance",
        )
        assert q.ticker == "MSFT"

    def test_optional_fields_none(self) -> None:
        q = Quote(
            ticker="MSFT",
            timestamp=datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
            bid=None,
            ask=None,
            bid_size=None,
            ask_size=None,
            last=Decimal("375.00"),
            last_size=None,
            volume=None,
            open=None,
            high=None,
            low=None,
            close=None,
            change=None,
            change_pct=None,
            provider="yfinance",
        )
        assert q.bid is None


class TestTickerInfo:
    def test_valid(self) -> None:
        t = TickerInfo(
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
        assert t.ticker == "AAPL"
        assert t.market_cap == 3_000_000_000_000

    def test_optional_fields_none(self) -> None:
        t = TickerInfo(
            ticker="AAPL",
            name="Apple Inc.",
            exchange="NASDAQ",
            currency="USD",
            country=None,
            sector=None,
            industry=None,
            market_cap=None,
            provider="yfinance",
        )
        assert t.country is None


class TestStockFeedResponse:
    def test_valid_with_ohlcv_list(self) -> None:
        bar = make_ohlcv()
        resp: StockFeedResponse[list[OHLCVBar]] = StockFeedResponse(
            data=[bar],
            provider_used="yfinance",
            cache_hit=False,
            latency_ms=42.5,
            timestamp=datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
            interval=Interval.ONE_DAY,
            ticker="AAPL",
        )
        assert resp.cache_hit is False
        assert len(resp.data) == 1

    def test_optional_interval_and_ticker(self) -> None:
        resp: StockFeedResponse[dict[str, object]] = StockFeedResponse(
            data={},
            provider_used="yfinance",
            cache_hit=True,
            latency_ms=1.0,
            timestamp=datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
            interval=None,
            ticker=None,
        )
        assert resp.interval is None
        assert resp.ticker is None


class TestModelValidators:
    def test_quote_empty_ticker_raises(self) -> None:
        from datetime import datetime, timezone
        from decimal import Decimal

        with pytest.raises(PydanticValidationError):
            Quote(
                ticker="  ",
                provider="test",
                timestamp=datetime.now(timezone.utc),
                last=Decimal("100"),
                bid=None, ask=None, bid_size=None, ask_size=None,
                last_size=None, volume=None, open=None, high=None,
                low=None, close=None, change=None, change_pct=None,
            )

    def test_ticker_info_empty_ticker_raises(self) -> None:
        with pytest.raises(PydanticValidationError):
            TickerInfo(
                ticker="",
                provider="test",
                name="Test",
                exchange="NYSE",
                currency="USD",
                sector=None, industry=None, market_cap=None,
                description=None, website=None, logo_url=None,
                phone=None, country=None,
            )


class TestNormalizerBase:
    def test_require_fields_raises_on_missing(self) -> None:
        from stockfeed.exceptions import ValidationError as SFValidationError
        from stockfeed.normalizer.base import BaseNormalizer

        class _N(BaseNormalizer):
            def normalize_ohlcv(self, raw):  # type: ignore[override]
                return []
            def normalize_quote(self, raw):  # type: ignore[override]
                return None
            def normalize_ticker_info(self, raw):  # type: ignore[override]
                return None

        n = _N()
        with pytest.raises(SFValidationError):
            n._require({"a": 1}, "b", "c")
        # Test with context to exercise the label path
        with pytest.raises(SFValidationError):
            n._require({"a": 1}, "b", context="mydata")
