"""Unit tests for CacheManager."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from stockfeed.cache.manager import CacheManager, DateRange
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bar(ticker: str = "AAPL", days_offset: int = 0) -> OHLCVBar:
    ts = datetime(2024, 1, 2 + days_offset, tzinfo=timezone.utc)
    return OHLCVBar(
        ticker=ticker,
        timestamp=ts,
        interval=Interval.ONE_DAY,
        open=Decimal("185.50"),
        high=Decimal("188.44"),
        low=Decimal("183.00"),
        close_raw=Decimal("187.20"),
        close_adj=Decimal("187.20"),
        volume=1000000,
        vwap=None,
        trade_count=None,
        provider="test",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCacheManager:
    def test_write_and_read_full_hit(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)
        bars = [_make_bar(days_offset=0), _make_bar(days_offset=1)]
        cm.write(bars)

        result = cm.read(
            "AAPL",
            Interval.ONE_DAY,
            start=datetime(2024, 1, 2, tzinfo=timezone.utc),
            end=datetime(2024, 1, 4, tzinfo=timezone.utc),
        )
        assert result is not None
        assert len(result) == 2

    def test_read_miss_returns_none(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)

        result = cm.read(
            "AAPL",
            Interval.ONE_DAY,
            start=datetime(2024, 1, 2, tzinfo=timezone.utc),
            end=datetime(2024, 1, 4, tzinfo=timezone.utc),
        )
        assert result is None

    def test_read_partial_full_miss(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)

        start = datetime(2024, 1, 2, tzinfo=timezone.utc)
        end = datetime(2024, 1, 4, tzinfo=timezone.utc)
        bars, missing = cm.read_partial("AAPL", Interval.ONE_DAY, start, end)

        assert bars == []
        assert len(missing) == 1
        assert isinstance(missing[0], DateRange)
        assert missing[0].start == start
        assert missing[0].end == end

    def test_read_partial_full_hit(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)
        bars_to_write = [_make_bar(days_offset=0), _make_bar(days_offset=1)]
        cm.write(bars_to_write)

        bars, missing = cm.read_partial(
            "AAPL",
            Interval.ONE_DAY,
            start=datetime(2024, 1, 2, tzinfo=timezone.utc),
            end=datetime(2024, 1, 4, tzinfo=timezone.utc),
        )
        assert len(bars) == 2
        assert missing == []

    def test_write_upsert_no_duplicates(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)
        bar = _make_bar(days_offset=0)
        cm.write([bar])
        cm.write([bar])

        stats = cm.stats()
        assert stats.row_count == 1

    def test_invalidate_by_ticker(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)
        cm.write([_make_bar("AAPL"), _make_bar("MSFT")])

        cm.invalidate(ticker="AAPL")

        stats = cm.stats()
        assert stats.row_count == 1

        # MSFT remains
        msft_result = cm.read(
            "MSFT",
            Interval.ONE_DAY,
            start=datetime(2024, 1, 2, tzinfo=timezone.utc),
            end=datetime(2024, 1, 3, tzinfo=timezone.utc),
        )
        assert msft_result is not None

    def test_invalidate_by_interval(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)

        daily_bar = _make_bar("AAPL", days_offset=0)
        # Write a weekly bar (same ticker, different interval)
        weekly_bar = OHLCVBar(
            ticker="AAPL",
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            interval=Interval.ONE_WEEK,
            open=Decimal("185.50"),
            high=Decimal("188.44"),
            low=Decimal("183.00"),
            close_raw=Decimal("187.20"),
            close_adj=Decimal("187.20"),
            volume=1000000,
            vwap=None,
            trade_count=None,
            provider="test",
        )
        cm.write([daily_bar, weekly_bar])

        cm.invalidate(interval=Interval.ONE_DAY)

        stats = cm.stats()
        assert stats.row_count == 1

    def test_invalidate_all(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)
        cm.write([_make_bar("AAPL"), _make_bar("MSFT")])

        cm.invalidate()

        stats = cm.stats()
        assert stats.row_count == 0

    def test_stats_empty(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)

        stats = cm.stats()
        assert stats.row_count == 0
        assert stats.oldest_entry is None
        assert stats.newest_entry is None

    def test_stats_with_data(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)
        bars = [_make_bar(days_offset=0), _make_bar(days_offset=1)]
        cm.write(bars)

        stats = cm.stats()
        assert stats.row_count == 2
        assert stats.oldest_entry is not None
        assert stats.newest_entry is not None
        assert stats.oldest_entry <= stats.newest_entry
