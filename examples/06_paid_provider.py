"""Example 6 — Using a paid provider (Tiingo).

Requires STOCKFEED_TIINGO_API_KEY set in your environment or .env file.

Run:
    STOCKFEED_TIINGO_API_KEY=your_key python examples/06_paid_provider.py
"""

import os

from stockfeed.config import StockFeedSettings
from stockfeed.exceptions import ProviderAuthError, TickerNotFoundError
from stockfeed.models.interval import Interval
from stockfeed.providers.tiingo.provider import TiingoProvider
from datetime import datetime, timezone

settings = StockFeedSettings()
api_key = settings.tiingo_api_key or os.getenv("TIINGO_API_KEY", "")

if not api_key:
    print("No Tiingo API key found. Set STOCKFEED_TIINGO_API_KEY and re-run.")
    print("Falling back to yfinance for this demo...\n")
    from stockfeed.providers.yfinance.provider import YFinanceProvider
    provider = YFinanceProvider()  # type: ignore[assignment]
    using = "yfinance"
else:
    provider = TiingoProvider(api_key=api_key)  # type: ignore[assignment]
    using = "tiingo"

try:
    bars = provider.get_ohlcv(  # type: ignore[union-attr]
        "SPY",
        Interval.ONE_DAY,
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 10, tzinfo=timezone.utc),
    )
    print(f"Fetched {len(bars)} bars via {using}")
    for bar in bars:
        print(f"  {bar.timestamp.date()}  close={bar.close_raw}  adj={bar.close_adj}")
except ProviderAuthError as e:
    print(f"Authentication error: {e}")
    print("Check that your API key is valid.")
except TickerNotFoundError as e:
    print(f"Ticker not found: {e}")
