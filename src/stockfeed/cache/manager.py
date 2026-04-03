"""CacheManager — read/write/invalidate OHLCV bars in DuckDB."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from stockfeed.cache.connection import get_connection
from stockfeed.cache.schema import run_migrations
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar


@dataclass(frozen=True)
class DateRange:
    """An inclusive [start, end) date range that is missing from the cache."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class CacheStats:
    """Summary statistics about the OHLCV cache."""

    row_count: int
    size_bytes: int
    oldest_entry: datetime | None
    newest_entry: datetime | None


def _row_to_bar(row: tuple[Any, ...]) -> OHLCVBar:
    (
        ticker,
        ts,
        interval,
        open_,
        high,
        low,
        close_raw,
        close_adj,
        volume,
        vwap,
        trade_count,
        provider,
    ) = row
    # DuckDB returns timestamps as datetime objects; ensure UTC
    if isinstance(ts, datetime):
        dt = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
    else:
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)

    return OHLCVBar(
        ticker=ticker,
        timestamp=dt,
        interval=Interval(interval),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close_raw=Decimal(str(close_raw)),
        close_adj=Decimal(str(close_adj)) if close_adj is not None else None,
        volume=int(volume),
        vwap=Decimal(str(vwap)) if vwap is not None else None,
        trade_count=int(trade_count) if trade_count is not None else None,
        provider=provider,
    )


class CacheManager:
    """Read/write/invalidate OHLCV bars in a DuckDB cache.

    Parameters
    ----------
    db_path : str
        Path to the DuckDB file. Defaults to ``~/.stockfeed/cache.db``.
    """

    def __init__(self, db_path: str = "~/.stockfeed/cache.db") -> None:
        self._db_path = db_path
        conn = get_connection(db_path)
        run_migrations(conn)

    @property
    def _conn(self):  # type: ignore[no-untyped-def]
        return get_connection(self._db_path)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read(
        self,
        ticker: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar] | None:
        """Return cached bars for the full [start, end) range, or ``None`` on any miss.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.
        interval : Interval
            Bar width.
        start : datetime
            Inclusive start (UTC).
        end : datetime
            Exclusive end (UTC).

        Returns
        -------
        list[OHLCVBar] | None
            Sorted bars, or ``None`` if the cache doesn't cover the full range.
        """
        rows = self._conn.execute(
            """
            SELECT ticker, timestamp, interval, open, high, low, close_raw, close_adj,
                   volume, vwap, trade_count, provider
            FROM ohlcv
            WHERE ticker = ? AND interval = ? AND timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC
            """,
            [ticker.upper(), interval.value, start, end],
        ).fetchall()

        if not rows:
            return None

        bars = [_row_to_bar(r) for r in rows]

        # Verify full coverage: no gaps
        cached_start = bars[0].timestamp
        cached_end = bars[-1].timestamp
        if cached_start > start or cached_end < _last_bar_before(end, interval):
            return None

        return bars

    def read_partial(
        self,
        ticker: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> tuple[list[OHLCVBar], list[DateRange]]:
        """Return cached bars and a list of missing date ranges.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.
        interval : Interval
            Bar width.
        start : datetime
            Inclusive start (UTC).
        end : datetime
            Exclusive end (UTC).

        Returns
        -------
        tuple[list[OHLCVBar], list[DateRange]]
            ``(cached_bars, missing_ranges)`` — missing_ranges is empty on full hit,
            contains the entire [start, end) on complete miss.
        """
        rows = self._conn.execute(
            """
            SELECT ticker, timestamp, interval, open, high, low, close_raw, close_adj,
                   volume, vwap, trade_count, provider
            FROM ohlcv
            WHERE ticker = ? AND interval = ? AND timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC
            """,
            [ticker.upper(), interval.value, start, end],
        ).fetchall()

        if not rows:
            return [], [DateRange(start=start, end=end)]

        bars = [_row_to_bar(r) for r in rows]
        missing: list[DateRange] = []

        # Gap before first cached bar
        if bars[0].timestamp > start:
            missing.append(DateRange(start=start, end=bars[0].timestamp))

        # Gap after last cached bar
        if bars[-1].timestamp < _last_bar_before(end, interval):
            missing.append(DateRange(start=_next_bar(bars[-1].timestamp, interval), end=end))

        return bars, missing

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(self, bars: list[OHLCVBar]) -> None:
        """Upsert bars into the cache (no duplicates on primary key conflict).

        Parameters
        ----------
        bars : list[OHLCVBar]
            Bars to persist.
        """
        if not bars:
            return

        rows = [
            (
                b.ticker.upper(),
                b.timestamp.astimezone(timezone.utc),
                b.interval.value,
                str(b.open),
                str(b.high),
                str(b.low),
                str(b.close_raw),
                str(b.close_adj) if b.close_adj is not None else None,
                b.volume,
                str(b.vwap) if b.vwap is not None else None,
                b.trade_count,
                b.provider,
            )
            for b in bars
        ]

        self._conn.executemany(
            """
            INSERT OR REPLACE INTO ohlcv
                (ticker, timestamp, interval, open, high, low, close_raw, close_adj,
                 volume, vwap, trade_count, provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    # ------------------------------------------------------------------
    # Invalidate
    # ------------------------------------------------------------------

    def invalidate(
        self,
        ticker: str | None = None,
        interval: Interval | None = None,
        before: datetime | None = None,
    ) -> int:
        """Delete cache rows matching the given filters.

        All arguments are optional; if none are given, the entire cache is cleared.

        Parameters
        ----------
        ticker : str | None
            Only delete rows for this ticker.
        interval : Interval | None
            Only delete rows for this interval.
        before : datetime | None
            Only delete rows with timestamp < before.

        Returns
        -------
        int
            Number of rows deleted.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if ticker is not None:
            clauses.append("ticker = ?")
            params.append(ticker.upper())
        if interval is not None:
            clauses.append("interval = ?")
            params.append(interval.value)
        if before is not None:
            clauses.append("timestamp < ?")
            params.append(before)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        # Count before delete so we can return the number of deleted rows.
        # DuckDB does not support changes() (SQLite-only), so we count manually.
        count_before: int = self._conn.execute(
            f"SELECT COUNT(*) FROM ohlcv {where}", params
        ).fetchone()[0]
        self._conn.execute(f"DELETE FROM ohlcv {where}", params)
        return count_before

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> CacheStats:
        """Return summary statistics about the cache.

        Returns
        -------
        CacheStats
            Row count, disk size, oldest and newest entry timestamps.
        """
        row = self._conn.execute(
            "SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM ohlcv"
        ).fetchone()
        assert row is not None  # noqa: S101

        count, oldest, newest = row

        # Disk size from DuckDB pragma
        size_bytes = 0
        resolved = str(Path(self._db_path).expanduser().resolve())
        p = Path(resolved)
        if p.exists():
            size_bytes = p.stat().st_size

        def _to_utc(ts: Any) -> datetime | None:
            if ts is None:
                return None
            if isinstance(ts, datetime):
                return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)

        return CacheStats(
            row_count=int(count),
            size_bytes=size_bytes,
            oldest_entry=_to_utc(oldest),
            newest_entry=_to_utc(newest),
        )


# ------------------------------------------------------------------
# Interval arithmetic helpers
# ------------------------------------------------------------------

_INTERVAL_SECONDS: dict[Interval, int] = {
    Interval.ONE_MINUTE: 60,
    Interval.FIVE_MINUTES: 300,
    Interval.FIFTEEN_MINUTES: 900,
    Interval.THIRTY_MINUTES: 1800,
    Interval.ONE_HOUR: 3600,
    Interval.FOUR_HOURS: 14400,
    Interval.ONE_DAY: 86400,
    Interval.ONE_WEEK: 604800,
    Interval.ONE_MONTH: 2592000,  # ~30 days; good enough for gap detection
}


def _interval_seconds(interval: Interval) -> int:
    return _INTERVAL_SECONDS[interval]


def _last_bar_before(end: datetime, interval: Interval) -> datetime:
    """Return the latest bar timestamp that would fall before *end*."""
    from datetime import timedelta

    return end - timedelta(seconds=_interval_seconds(interval))


def _next_bar(ts: datetime, interval: Interval) -> datetime:
    from datetime import timedelta

    return ts + timedelta(seconds=_interval_seconds(interval))
