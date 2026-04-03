"""Unit tests for MarketHoursChecker."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from stockfeed.cache.market_hours import MarketHoursChecker
from stockfeed.models.interval import Interval


class TestMarketHoursChecker:
    def setup_method(self) -> None:
        self.checker = MarketHoursChecker()

    def test_daily_interval_always_uses_cache(self) -> None:
        for interval in (Interval.ONE_DAY, Interval.ONE_WEEK, Interval.ONE_MONTH):
            assert self.checker.should_use_cache(interval) is True

    def test_intraday_uses_cache_when_market_closed(self) -> None:
        with patch.object(self.checker, "is_market_open", return_value=False):
            result = self.checker.should_use_cache(Interval.ONE_MINUTE, exchange="XNYS")
        assert result is True

    def test_intraday_bypasses_cache_when_market_open(self) -> None:
        with patch.object(self.checker, "is_market_open", return_value=True):
            result = self.checker.should_use_cache(Interval.ONE_HOUR, exchange="XNYS")
        assert result is False

    def test_unknown_exchange_falls_back_to_default(self) -> None:
        # Should not raise; falls back to default NYSE calendar
        try:
            result = self.checker.should_use_cache(
                Interval.ONE_DAY,
                exchange="UNKNOWN_EXCHANGE",
                dt=datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc),
            )
            assert isinstance(result, bool)
        except Exception as exc:
            pytest.fail(f"should_use_cache raised unexpectedly: {exc}")

    def test_should_use_cache_five_minutes_closed(self) -> None:
        with patch.object(self.checker, "is_market_open", return_value=False):
            assert self.checker.should_use_cache(Interval.FIVE_MINUTES) is True

    def test_should_use_cache_four_hours_open(self) -> None:
        with patch.object(self.checker, "is_market_open", return_value=True):
            assert self.checker.should_use_cache(Interval.FOUR_HOURS) is False

    def test_is_market_open_returns_bool(self) -> None:
        # Does not raise; weekend is closed
        result = self.checker.is_market_open(
            "XNYS", dt=datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc)
        )  # Saturday
        assert isinstance(result, bool)
        assert result is False

    def test_is_market_open_weekday_outside_hours(self) -> None:
        # 3am UTC on a Tuesday = well outside NYSE hours
        result = self.checker.is_market_open(
            "XNYS", dt=datetime(2024, 1, 2, 3, 0, tzinfo=timezone.utc)
        )
        assert isinstance(result, bool)

    def test_is_market_open_with_mapped_exchange(self) -> None:
        # NMS maps to XNAS
        result = self.checker.is_market_open(
            "NMS", dt=datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc)
        )  # Saturday
        assert result is False

    def test_get_calendar_caches_result(self) -> None:
        cal1 = self.checker._get_calendar("XNYS")
        cal2 = self.checker._get_calendar("XNYS")
        assert cal1 is cal2

    def test_get_calendar_unknown_falls_back(self) -> None:
        # Should not raise; uses default
        cal = self.checker._get_calendar("UNKNOWN_EXCHANGE_XYZ")
        assert cal is not None

    def test_should_use_cache_with_dt(self) -> None:
        # Pass a specific dt to exercise the dt code path
        result = self.checker.should_use_cache(
            Interval.ONE_DAY,
            exchange="XNYS",
            dt=datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc),
        )
        assert result is True  # ONE_DAY always uses cache
