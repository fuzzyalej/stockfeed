"""Integration tests for end-to-end cache read/write flow."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from stockfeed.cache.manager import CacheManager
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bar(ticker: str = "AAPL", days_offset: int = 0) -> OHLCVBar:
    ts = datetime(2024, 1, 1 + days_offset, tzinfo=timezone.utc)
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
# Integration tests
# ---------------------------------------------------------------------------


class TestCacheFlow:
    def test_cold_start_then_warm_hit(self, tmp_path: object) -> None:
        """Write bars to cache, then read them back — second read is non-None."""
        db = str(tmp_path / "cache.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)

        # Cold start — nothing in cache
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 3, tzinfo=timezone.utc)
        cold = cm.read("AAPL", Interval.ONE_DAY, start, end)
        assert cold is None

        # Write two days of bars
        bars = [_make_bar(days_offset=0), _make_bar(days_offset=1)]
        cm.write(bars)

        # Warm hit — should now return bars
        warm = cm.read("AAPL", Interval.ONE_DAY, start, end)
        assert warm is not None
        assert len(warm) == 2
        assert warm[0].ticker == "AAPL"

    def test_invalidate_clears_data(self, tmp_path: object) -> None:
        """Write bars, invalidate, read returns None."""
        db = str(tmp_path / "cache.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)

        bars = [_make_bar(days_offset=0), _make_bar(days_offset=1)]
        cm.write(bars)

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 3, tzinfo=timezone.utc)

        # Confirm data is present
        before = cm.read("AAPL", Interval.ONE_DAY, start, end)
        assert before is not None

        # Invalidate all
        cm.invalidate()

        # Now read returns None
        after = cm.read("AAPL", Interval.ONE_DAY, start, end)
        assert after is None

    def test_partial_hit_detection(self, tmp_path: object) -> None:
        """Write bars for Jan 1-5, read Jan 1-10, verify missing range is Jan 6-10."""
        db = str(tmp_path / "cache.db")  # type: ignore[operator]
        cm = CacheManager(db_path=db)

        # Write Jan 1 through Jan 5 (offsets 0-4)
        bars = [_make_bar(days_offset=i) for i in range(5)]
        cm.write(bars)

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 11, tzinfo=timezone.utc)

        cached_bars, missing = cm.read_partial("AAPL", Interval.ONE_DAY, start, end)

        # Should have the 5 cached bars
        assert len(cached_bars) == 5

        # Should have at least one missing range covering the gap
        assert len(missing) >= 1

        # The missing range should start at or after Jan 6
        gap_start = missing[-1].start
        assert gap_start >= datetime(2024, 1, 6, tzinfo=timezone.utc)
        assert gap_start <= datetime(2024, 1, 7, tzinfo=timezone.utc)

        # The missing range end should equal the requested end
        assert missing[-1].end == end
