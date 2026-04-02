"""Example 1 — Fetch daily OHLCV bars from yfinance.

yfinance requires no API key and is always available.
Run:
    python examples/01_ohlcv_yfinance.py
"""

from datetime import datetime, timezone

from stockfeed.models.interval import Interval
from stockfeed.providers.yfinance.provider import YFinanceProvider

provider = YFinanceProvider()

bars = provider.get_ohlcv(
    "AAPL",
    Interval.ONE_DAY,
    start=datetime(2024, 1, 1, tzinfo=timezone.utc),
    end=datetime(2024, 1, 31, tzinfo=timezone.utc),
)

print(f"Fetched {len(bars)} bars for AAPL (1d) via {bars[0].provider}\n")
print(f"{'Date':<12} {'Open':>10} {'Close':>10} {'Adj Close':>10} {'Volume':>12}")
print("-" * 58)
for bar in bars:
    adj = f"{bar.close_adj:.2f}" if bar.close_adj else "—"
    print(
        f"{bar.timestamp.date()!s:<12}"
        f" {float(bar.open):>10.2f}"
        f" {float(bar.close_raw):>10.2f}"
        f" {adj:>10}"
        f" {bar.volume:>12,}"
    )
