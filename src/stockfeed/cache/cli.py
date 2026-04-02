"""Cache CLI — ``python -m stockfeed.cache`` entry point.

Subcommands
-----------
stats
    Print cache statistics (row count, size, date range).
clear
    Remove rows matching optional --ticker / --interval / --before filters.
export
    Export cache to CSV or Parquet.
inspect
    Print cached rows for a specific ticker + interval.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from stockfeed.cache.connection import get_connection
from stockfeed.cache.manager import CacheManager
from stockfeed.cache.schema import run_migrations
from stockfeed.models.interval import Interval


def _get_manager(db_path: str) -> CacheManager:
    return CacheManager(db_path=db_path)


# ------------------------------------------------------------------
# stats
# ------------------------------------------------------------------


def cmd_stats(args: argparse.Namespace) -> None:
    mgr = _get_manager(args.db)
    s = mgr.stats()
    print(f"Rows     : {s.row_count:,}")
    print(f"Size     : {s.size_bytes / 1024:.1f} KB")
    print(f"Oldest   : {s.oldest_entry or '—'}")
    print(f"Newest   : {s.newest_entry or '—'}")


# ------------------------------------------------------------------
# clear
# ------------------------------------------------------------------


def cmd_clear(args: argparse.Namespace) -> None:
    mgr = _get_manager(args.db)
    interval = Interval(args.interval) if args.interval else None
    before: datetime | None = None
    if args.before:
        before = datetime.fromisoformat(args.before).replace(tzinfo=timezone.utc)

    deleted = mgr.invalidate(ticker=args.ticker, interval=interval, before=before)
    print(f"Deleted {deleted} row(s).")


# ------------------------------------------------------------------
# export
# ------------------------------------------------------------------


def cmd_export(args: argparse.Namespace) -> None:
    conn = get_connection(args.db)
    run_migrations(conn)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    fmt = args.format.lower()
    if fmt == "csv":
        dest = out / "ohlcv.csv"
        conn.execute(f"COPY ohlcv TO '{dest}' (FORMAT CSV, HEADER TRUE)")
        print(f"Exported to {dest}")
    elif fmt == "parquet":
        dest = out / "ohlcv.parquet"
        conn.execute(f"COPY ohlcv TO '{dest}' (FORMAT PARQUET)")
        print(f"Exported to {dest}")
    else:
        print(f"Unknown format: {fmt}. Use csv or parquet.", file=sys.stderr)
        sys.exit(1)


# ------------------------------------------------------------------
# inspect
# ------------------------------------------------------------------


def cmd_inspect(args: argparse.Namespace) -> None:
    conn = get_connection(args.db)
    run_migrations(conn)

    where_clauses = ["ticker = ?"]
    params: list[object] = [args.ticker.upper()]

    if args.interval:
        where_clauses.append("interval = ?")
        params.append(args.interval)

    where = " AND ".join(where_clauses)
    rows = conn.execute(
        f"""
        SELECT ticker, timestamp, interval, open, high, low, close_raw, close_adj,
               volume, provider
        FROM ohlcv
        WHERE {where}
        ORDER BY timestamp ASC
        LIMIT 100
        """,
        params,
    ).fetchall()

    if not rows:
        print("No rows found.")
        return

    header = f"{'Ticker':<8} {'Timestamp':<26} {'Interval':<6} {'Open':>10} {'Close':>10} {'Volume':>12} {'Provider'}"
    print(header)
    print("-" * len(header))
    for r in rows:
        ticker, ts, interval, open_, _high, _low, close_raw, _adj, volume, provider = r
        print(f"{ticker:<8} {str(ts):<26} {interval:<6} {float(open_):>10.4f} {float(close_raw):>10.4f} {int(volume):>12,} {provider}")

    print(f"\n{len(rows)} row(s) shown (max 100).")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m stockfeed.cache",
        description="Inspect and manage the stockfeed DuckDB cache.",
    )
    parser.add_argument(
        "--db",
        default="~/.stockfeed/cache.db",
        help="Path to the DuckDB cache file (default: ~/.stockfeed/cache.db)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # stats
    sub.add_parser("stats", help="Print cache statistics")

    # clear
    p_clear = sub.add_parser("clear", help="Remove cached rows")
    p_clear.add_argument("--ticker", help="Only clear rows for this ticker")
    p_clear.add_argument("--interval", help="Only clear rows for this interval (e.g. 1d)")
    p_clear.add_argument("--before", help="Only clear rows before this date (ISO 8601)")

    # export
    p_export = sub.add_parser("export", help="Export cache to CSV or Parquet")
    p_export.add_argument("--format", default="csv", choices=["csv", "parquet"])
    p_export.add_argument("--output", default="./stockfeed_export", help="Output directory")

    # inspect
    p_inspect = sub.add_parser("inspect", help="Print cached rows for a ticker")
    p_inspect.add_argument("--ticker", required=True)
    p_inspect.add_argument("--interval", help="Filter by interval")

    args = parser.parse_args(argv)

    dispatch = {
        "stats": cmd_stats,
        "clear": cmd_clear,
        "export": cmd_export,
        "inspect": cmd_inspect,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
