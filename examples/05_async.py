"""Example 5 — Async data fetching with AsyncStockFeedClient.

Fetches OHLCV bars for multiple tickers concurrently using asyncio.
Provider selection is automatic — yfinance is used by default.

Run:
    python examples/05_async.py
"""

import asyncio

from stockfeed import AsyncStockFeedClient

client = AsyncStockFeedClient()

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN"]


async def fetch(ticker: str) -> tuple[str, int]:
    bars = await client.get_ohlcv(ticker, "1d", "2024-06-01", "2024-06-30")
    return ticker, len(bars)


async def main() -> None:
    print(f"Fetching {len(TICKERS)} tickers concurrently...\n")
    results = await asyncio.gather(*[fetch(t) for t in TICKERS])
    for ticker, count in results:
        print(f"  {ticker:<8} {count} bars")


asyncio.run(main())
