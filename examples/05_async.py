"""Example 5 — Async data fetching.

Fetches OHLCV bars for multiple tickers concurrently using asyncio.
yfinance is synchronous under the hood; async_get_ohlcv uses
asyncio.to_thread so it doesn't block the event loop.

Run:
    python examples/05_async.py
"""

import asyncio
from datetime import datetime, timezone

from stockfeed.models.interval import Interval
from stockfeed.providers.yfinance.provider import YFinanceProvider

provider = YFinanceProvider()

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN"]
START = datetime(2024, 6, 1, tzinfo=timezone.utc)
END = datetime(2024, 6, 30, tzinfo=timezone.utc)


async def fetch(ticker: str) -> tuple[str, int]:
    bars = await provider.async_get_ohlcv(ticker, Interval.ONE_DAY, START, END)
    return ticker, len(bars)


async def main() -> None:
    print(f"Fetching {len(TICKERS)} tickers concurrently...\n")
    results = await asyncio.gather(*[fetch(t) for t in TICKERS])
    for ticker, count in results:
        print(f"  {ticker:<8} {count} bars")


asyncio.run(main())
