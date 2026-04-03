# Getting Started

## Installation

```bash
pip install stockfeed
```

For SSE streaming support (optional):

```bash
pip install "stockfeed[streaming]"
```

## First OHLCV call

No API key needed — `yfinance` is always the free fallback:

```python
from stockfeed import StockFeedClient

client = StockFeedClient()
bars = client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-31")

for bar in bars:
    print(bar.timestamp.date(), bar.close_raw, bar.close_adj)
```

Dates can be `"YYYY-MM-DD"` strings (parsed as UTC midnight) or `datetime` objects:

```python
from datetime import datetime, timezone

bars = client.get_ohlcv(
    "AAPL",
    "1d",
    datetime(2024, 1, 1, tzinfo=timezone.utc),
    datetime(2024, 1, 31, tzinfo=timezone.utc),
)
```

## Configure providers

Set API keys in your environment or `.env` file:

```env
STOCKFEED_TIINGO_API_KEY=your_key
STOCKFEED_FINNHUB_API_KEY=your_key
STOCKFEED_TWELVEDATA_API_KEY=your_key
STOCKFEED_ALPACA_API_KEY=your_key
STOCKFEED_ALPACA_SECRET_KEY=your_secret
STOCKFEED_TRADIER_API_KEY=your_key
```

Or configure programmatically:

```python
from stockfeed import StockFeedClient, StockFeedSettings

settings = StockFeedSettings(tiingo_api_key="your_key")
client = StockFeedClient(settings=settings)
```

Once a provider's key is configured, `stockfeed` will prefer it over `yfinance`.

## Understanding the response

`get_ohlcv()` returns a plain `list[OHLCVBar]`. Each bar has:

```python
bar.ticker        # "AAPL"
bar.timestamp     # datetime (always UTC)
bar.interval      # Interval.ONE_DAY
bar.open          # Decimal
bar.high          # Decimal
bar.low           # Decimal
bar.close_raw     # Decimal — unadjusted close
bar.close_adj     # Decimal | None — split/dividend-adjusted
bar.volume        # int
bar.vwap          # Decimal | None
bar.trade_count   # int | None
bar.provider      # "yfinance", "tiingo", etc.
```

Both `close_raw` and `close_adj` are always exposed. For providers that don't return adjusted prices, `close_adj` is `None`.

## Quote and company info

```python
quote = client.get_quote("MSFT")
print(quote.last, quote.bid, quote.ask)

info = client.get_ticker_info("MSFT")
print(info.name, info.sector, info.market_cap)
```

## Async client

`AsyncStockFeedClient` has an identical method surface but all methods are `async`:

```python
import asyncio
from stockfeed import AsyncStockFeedClient

async def main():
    client = AsyncStockFeedClient()

    # Concurrent fetch
    aapl, msft = await asyncio.gather(
        client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-31"),
        client.get_ohlcv("MSFT", "1d", "2024-01-01", "2024-01-31"),
    )

asyncio.run(main())
```

## Pinning a provider

Pass `provider="tiingo"` to any method to skip auto-selection:

```python
bars = client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-31", provider="tiingo")
```

If the pinned provider fails, `yfinance` is still tried as the final fallback.

## Error handling

All exceptions inherit from `StockFeedError`:

```python
from stockfeed.exceptions import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    TickerNotFoundError,
)

try:
    bars = client.get_ohlcv("INVALID", "1d", "2024-01-01", "2024-01-31")
except TickerNotFoundError as e:
    print(f"{e.ticker} not found on {e.provider}. {e.suggestion}")
except ProviderRateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after}s")
except ProviderUnavailableError:
    print("All providers failed")
```
