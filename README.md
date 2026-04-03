# stockfeed

Unified market data access for Python — stocks, futures, options, and crypto.

`stockfeed` is a professional-grade library that abstracts multiple data providers behind a single, fully-typed API. It handles provider failover automatically, caches results in an embedded DuckDB database, and exposes identical sync and async interfaces.

## Features

- **One API, many providers** — yfinance (free, always available), Tiingo, Finnhub, Twelve Data, Alpaca, Tradier, CoinGecko
- **Transparent failover** — if a provider is rate-limited or down, the next one is tried automatically; yfinance is always the final fallback
- **Cache-first** — all requests check DuckDB first; on a miss, data is fetched, stored, and returned
- **Dual interface** — `StockFeedClient` (sync) and `AsyncStockFeedClient` (async) with identical method surfaces
- **Canonical models** — every provider returns the same `OHLCVBar`, `Quote`, and `TickerInfo` types
- **Both adjusted and raw prices** — `OHLCVBar.close_raw` and `OHLCVBar.close_adj` are always separate fields
- **Fully typed** — passes `mypy --strict` across all 50 source files

## Installation

```bash
pip install stockfeed
```

For optional provider extras (coming in later phases):

```bash
pip install "stockfeed[streaming]"   # SSE streaming support
```

## Quick start

### OHLCV bars (no API key needed)

```python
from datetime import datetime, timezone
from stockfeed import StockFeedClient
from stockfeed.models.interval import Interval

client = StockFeedClient()

bars = client.get_ohlcv(
    "AAPL",
    Interval.ONE_DAY,
    start=datetime(2024, 1, 1, tzinfo=timezone.utc),
    end=datetime(2024, 1, 31, tzinfo=timezone.utc),
)

for bar in bars:
    print(bar.timestamp.date(), bar.close_raw, bar.close_adj)
# 2024-01-02  185.64  183.73
# 2024-01-03  184.25  182.36
# ...
```

### Quote and company info

```python
from stockfeed import StockFeedClient

client = StockFeedClient()

quote = client.get_quote("MSFT")
print(quote.last, quote.bid, quote.ask)

info = client.get_ticker_info("MSFT")
print(info.name, info.sector, info.market_cap)
```

### Async — fetch multiple tickers concurrently

```python
import asyncio
from datetime import datetime, timezone
from stockfeed import AsyncStockFeedClient
from stockfeed.models.interval import Interval

async def main():
    client = AsyncStockFeedClient()
    tasks = [
        client.get_ohlcv(t, Interval.ONE_DAY,
            datetime(2024, 6, 1, tzinfo=timezone.utc),
            datetime(2024, 6, 30, tzinfo=timezone.utc))
        for t in ["AAPL", "MSFT", "GOOGL", "AMZN"]
    ]
    results = await asyncio.gather(*tasks)
    for bars in results:
        print(bars[0].ticker, len(bars), "bars")

asyncio.run(main())
```

### Using a paid provider (Tiingo)

```python
from stockfeed import StockFeedClient, StockFeedSettings
from stockfeed.exceptions import ProviderAuthError, TickerNotFoundError
from stockfeed.models.interval import Interval
from datetime import datetime, timezone

settings = StockFeedSettings(tiingo_api_key="your_tiingo_key")
# Or set STOCKFEED_TIINGO_API_KEY in env / .env
client = StockFeedClient(settings=settings)

try:
    bars = client.get_ohlcv("SPY", Interval.ONE_DAY,
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 10, tzinfo=timezone.utc),
        provider="tiingo")
except ProviderAuthError:
    print("Check your API key")
except TickerNotFoundError as e:
    print(f"{e.ticker} not found on {e.provider}")
```

### Cache management CLI

```bash
# Stats
python -m stockfeed.cache stats

# Clear one ticker
python -m stockfeed.cache clear --ticker AAPL

# Export to Parquet
python -m stockfeed.cache export --format parquet --output ./data/

# Inspect rows
python -m stockfeed.cache inspect --ticker AAPL --interval 1d
```

## Configuration

Settings are loaded from environment variables (prefix `STOCKFEED_`) or a `.env` file.

```env
# Provider API keys — omit any you don't have; those providers are skipped
STOCKFEED_TIINGO_API_KEY=your_key
STOCKFEED_FINNHUB_API_KEY=your_key
STOCKFEED_TWELVEDATA_API_KEY=your_key
STOCKFEED_ALPACA_API_KEY=your_key
STOCKFEED_ALPACA_SECRET_KEY=your_secret
STOCKFEED_TRADIER_API_KEY=your_key
STOCKFEED_COINGECKO_API_KEY=your_key   # optional, free tier works without it

# Cache
STOCKFEED_CACHE_PATH=~/.stockfeed/cache.db   # default
STOCKFEED_CACHE_ENABLED=true                 # default

# Logging
STOCKFEED_LOG_LEVEL=INFO
STOCKFEED_LOG_FORMAT=console   # or "json" for structured output
```

Or configure programmatically:

```python
from stockfeed import StockFeedClient, StockFeedSettings

settings = StockFeedSettings(tiingo_api_key="...", cache_path="/tmp/sf.db")
client = StockFeedClient(settings=settings)
```

## Supported intervals

| Enum | Value | Description |
|---|---|---|
| `Interval.ONE_MINUTE` | `"1m"` | 1-minute bars |
| `Interval.FIVE_MINUTES` | `"5m"` | 5-minute bars |
| `Interval.FIFTEEN_MINUTES` | `"15m"` | 15-minute bars |
| `Interval.THIRTY_MINUTES` | `"30m"` | 30-minute bars |
| `Interval.ONE_HOUR` | `"1h"` | Hourly bars |
| `Interval.FOUR_HOURS` | `"4h"` | 4-hour bars |
| `Interval.ONE_DAY` | `"1d"` | Daily bars |
| `Interval.ONE_WEEK` | `"1w"` | Weekly bars |
| `Interval.ONE_MONTH` | `"1mo"` | Monthly bars |

Not every provider supports every interval. `UnsupportedIntervalError` is raised if an interval isn't available on the selected provider.

## Providers

| Provider | Auth required | Notes |
|---|---|---|
| `yfinance` | No | Always available; final failover fallback |
| `tiingo` | Yes | Free tier available |
| `finnhub` | Yes | Free tier available |
| `twelvedata` | Yes | Free tier available |
| `alpaca` | Yes | Paper and live accounts |
| `tradier` | Yes | Brokerage API |
| `coingecko` | Optional | Crypto; free tier works without key |

Providers without API keys configured are skipped during selection. yfinance is always tried last.

## Error handling

All exceptions inherit from `StockFeedError` and carry structured context:

```python
from stockfeed import StockFeedClient
from stockfeed.exceptions import TickerNotFoundError, ProviderUnavailableError
from stockfeed.models.interval import Interval
from datetime import datetime, timezone

client = StockFeedClient()

try:
    bars = client.get_ohlcv("INVALID", Interval.ONE_DAY,
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 31, tzinfo=timezone.utc))
except TickerNotFoundError as e:
    print(e.ticker, e.provider, e.suggestion)
except ProviderUnavailableError as e:
    print(f"Provider {e.provider} is down")
```

| Exception | When raised |
|---|---|
| `ProviderAuthError` | Missing or invalid API key |
| `ProviderRateLimitError` | Rate limit exceeded (has `.retry_after`) |
| `ProviderUnavailableError` | Provider unreachable or server error |
| `TickerNotFoundError` | Ticker doesn't exist on this provider |
| `UnsupportedIntervalError` | Interval not supported by provider |
| `CacheReadError` / `CacheWriteError` | DuckDB cache I/O failure |
| `ValidationError` | Bad input (ticker format, date range, etc.) |
| `ConfigurationError` | Missing or invalid configuration |

## Development

```bash
git clone https://github.com/your-org/stockfeed
cd stockfeed
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

Run checks:

```bash
ruff check src/ tests/      # lint
ruff format src/ tests/     # format
mypy src/                   # type check
pytest                      # tests
```

## Examples

Working examples are in the [`examples/`](examples/) directory:

| File | What it shows |
|---|---|
| `01_ohlcv_yfinance.py` | Daily OHLCV bars with yfinance (no key needed) |
| `02_quote_and_ticker_info.py` | Live quote and company info |
| `03_cache.py` | Cache-first access — miss, write, hit, stats |
| `04_provider_health.py` | Registry inspection and health check |
| `05_async.py` | Concurrent fetching with `asyncio.gather` |
| `06_paid_provider.py` | Tiingo with auth and error handling |

Run any example after installing the library:

```bash
pip install -e ".[dev]"
python examples/01_ohlcv_yfinance.py
```

## Project status

| Phase | Description | Status |
|---|---|---|
| 1 | Project scaffold, models, config, exceptions, cache schema | Done |
| 2 | Provider abstraction layer, yfinance + stub providers | Done |
| 3 | Cache layer + HTTP providers (Tiingo, Finnhub, Twelve Data, Alpaca, Tradier) | Done |
| 4 | Sync & async clients, failover logic, ≥90% test coverage | Done |
| 5 | SSE streaming | Planned |
| 6 | Dev mode, CLI, MkDocs | Planned |

## License

MIT
