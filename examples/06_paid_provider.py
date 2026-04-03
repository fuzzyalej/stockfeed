"""Example 6 — Pinning a paid provider (Tiingo).

StockFeedClient handles everything — auth, failover, and caching — through
the same interface. Pass provider="tiingo" to use Tiingo specifically;
the client falls back to yfinance automatically if the key isn't set.

Set your key via environment variable or .env:
    STOCKFEED_TIINGO_API_KEY=your_key python examples/06_paid_provider.py

Run without a key to see automatic yfinance fallback:
    python examples/06_paid_provider.py
"""

from stockfeed import StockFeedClient, StockFeedSettings
from stockfeed.exceptions import ProviderAuthError, TickerNotFoundError

settings = StockFeedSettings()  # reads STOCKFEED_TIINGO_API_KEY from env / .env
client = StockFeedClient(settings=settings)

try:
    # provider="tiingo" pins Tiingo; falls back to yfinance if key is missing
    bars = client.get_ohlcv("SPY", "1d", "2024-01-01", "2024-01-10", provider="tiingo")
    print(f"Fetched {len(bars)} bars via {bars[0].provider}")
    for bar in bars:
        print(f"  {bar.timestamp.date()}  close={bar.close_raw}  adj={bar.close_adj}")
except ProviderAuthError as e:
    print(f"Authentication error: {e}")
    print("Set STOCKFEED_TIINGO_API_KEY and retry.")
except TickerNotFoundError as e:
    print(f"Ticker not found: {e}")
