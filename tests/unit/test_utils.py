"""Unit tests for stockfeed._utils helpers."""

from datetime import datetime, timezone

import pytest

from stockfeed._utils import parse_dt, parse_interval
from stockfeed.models.interval import Interval


class TestParseDt:
    def test_date_string_returns_utc_midnight(self) -> None:
        dt = parse_dt("2024-01-15")
        assert dt == datetime(2024, 1, 15, tzinfo=timezone.utc)
        assert dt.tzinfo is timezone.utc

    def test_datetime_string_returns_utc_second(self) -> None:
        dt = parse_dt("2024-01-15T09:30:00")
        assert dt == datetime(2024, 1, 15, 9, 30, 0, tzinfo=timezone.utc)

    def test_aware_datetime_passthrough(self) -> None:
        original = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        assert parse_dt(original) is original

    def test_naive_datetime_gets_utc(self) -> None:
        naive = datetime(2024, 6, 1, 12, 0)
        result = parse_dt(naive)
        assert result.tzinfo is timezone.utc
        assert result == datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)

    def test_invalid_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse date"):
            parse_dt("not-a-date")

    def test_wrong_format_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_dt("01/15/2024")


class TestParseInterval:
    def test_valid_string_returns_interval(self) -> None:
        assert parse_interval("1d") is Interval.ONE_DAY
        assert parse_interval("1h") is Interval.ONE_HOUR
        assert parse_interval("1m") is Interval.ONE_MINUTE
        assert parse_interval("1mo") is Interval.ONE_MONTH

    def test_interval_passthrough(self) -> None:
        iv = Interval.FIVE_MINUTES
        assert parse_interval(iv) is iv

    def test_invalid_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown interval"):
            parse_interval("2d")

    def test_error_message_lists_valid_values(self) -> None:
        with pytest.raises(ValueError, match="1d"):
            parse_interval("bad")
