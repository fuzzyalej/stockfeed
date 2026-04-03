"""Example 1 — Fetch daily OHLCV bars using StockFeedClient.

No API key needed — yfinance is always available as the default provider.

Run:
    python examples/01_ohlcv_yfinance.py
"""

from stockfeed import Interval, StockFeedClient

client = StockFeedClient()

bars = client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-31")

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
