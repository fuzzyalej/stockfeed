# stockfeed

[![PyPI version](https://img.shields.io/pypi/v/stockfeed.svg)](https://pypi.org/project/stockfeed/)
[![Python versions](https://img.shields.io/pypi/pyversions/stockfeed.svg)](https://pypi.org/project/stockfeed/)
[![Coverage](https://img.shields.io/badge/coverage-91%25-brightgreen.svg)](https://github.com/fuzzyalej/stockfeed)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Unified market data access for Python — stocks, futures, options, and crypto.

`stockfeed` is a professional-grade library that abstracts multiple data providers behind a single, fully-typed API. It handles provider failover automatically, caches results in an embedded DuckDB database, and exposes identical sync and async interfaces.

## Features

- **One API, many providers** — yfinance (free, always available), Tiingo, Finnhub, Twelve Data, Alpaca, Tradier, CoinGecko
- **Transparent failover** — if a provider is rate-limited or down, the next one is tried automatically; yfinance is always the final fallback
- **Cache-first** — all requests check DuckDB first; on a miss, data is fetched, stored, and returned
- **Dual interface** — `StockFeedClient` (sync) and `AsyncStockFeedClient` (async) with identical method surfaces
- **Canonical models** — every provider returns the same `OHLCVBar`, `Quote`, and `TickerInfo` types
- **Options data** — expiration dates, full options chains, and per-contract quotes with greeks (delta, gamma, theta, vega, rho); greeks come from the provider API where available, or are calculated via Black-Scholes
- **Both adjusted and raw prices** — `OHLCVBar.close_raw` and `OHLCVBar.close_adj` are always separate fields
- **Streaming** — `AsyncStockFeedClient.stream_quote()` polls a provider and yields live `Quote` objects
- **Dev simulator** — `AsyncStockFeedClient.simulate()` replays historical bars as a real-time stream for backtesting
- **Fully typed** — passes `mypy --strict` across all source files

## Installation

```bash
pip install stockfeed
```

For SSE streaming support:

```bash
pip install "stockfeed[streaming]"
```

## Quick start

```python
from stockfeed import StockFeedClient

client = StockFeedClient()
bars = client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-31")

for bar in bars:
    print(bar.timestamp.date(), bar.close_raw, bar.close_adj)
# 2024-01-02  185.64  183.73
# 2024-01-03  184.25  182.36
# ...
```

Date strings are parsed as UTC midnight. `datetime` objects are also accepted directly.

## Usage examples

### Quote and company info

```python
client = StockFeedClient()

quote = client.get_quote("MSFT")
print(quote.last, quote.bid, quote.ask)

info = client.get_ticker_info("MSFT")
print(info.name, info.sector, info.market_cap)
```

### Async — fetch multiple tickers concurrently

```python
import asyncio
from stockfeed import AsyncStockFeedClient

async def main():
    client = AsyncStockFeedClient()
    tasks = [
        client.get_ohlcv(t, "1d", "2024-06-01", "2024-06-30")
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

settings = StockFeedSettings(tiingo_api_key="your_tiingo_key")
# Or: STOCKFEED_TIINGO_API_KEY=... in env / .env
client = StockFeedClient(settings=settings)

try:
    bars = client.get_ohlcv("SPY", "1d", "2024-01-01", "2024-01-10", provider="tiingo")
except ProviderAuthError:
    print("Check your API key")
except TickerNotFoundError as e:
    print(f"{e.ticker} not found on {e.provider}")
```

### Live quote streaming (async)

```python
import asyncio
from stockfeed import AsyncStockFeedClient

async def main():
    client = AsyncStockFeedClient()
    async for quote in client.stream_quote("AAPL", interval=5.0):
        print(quote.last, quote.bid, quote.ask)

asyncio.run(main())
```

### Dev simulator — replay bars at speed

```python
import asyncio
from stockfeed import AsyncStockFeedClient

async def main():
    client = AsyncStockFeedClient(dev_mode=True)
    async for bar in client.simulate("AAPL", "2024-01-01", "2024-01-31", "1d", speed=0):
        print(bar.timestamp.date(), bar.close_raw)

asyncio.run(main())
```

### Options data

```python
from datetime import date
from stockfeed import StockFeedClient

client = StockFeedClient()

# List available expiration dates
expirations = client.get_option_expirations("AAPL")
print(expirations[:3])  # [date(2024, 1, 19), date(2024, 2, 16), ...]

# Fetch the options chain for a specific expiration
chain = client.get_options_chain("AAPL", expirations[0])
for contract in chain.contracts[:5]:
    print(
        contract.symbol,
        contract.option_type,
        contract.strike,
        contract.greeks.delta if contract.greeks else "—",
    )

# Quote a specific contract
quote = client.get_option_quote("AAPL240119C00150000")
print(quote.bid, quote.ask, quote.implied_volatility)
```

### Cache management CLI

```bash
python -m stockfeed.cache stats
python -m stockfeed.cache clear --ticker AAPL
python -m stockfeed.cache export --format parquet --output ./data/
python -m stockfeed.cache inspect --ticker AAPL --interval 1d
```

## Configuration

Settings load from environment variables (`STOCKFEED_` prefix) or a `.env` file:

```env
STOCKFEED_TIINGO_API_KEY=your_key
STOCKFEED_FINNHUB_API_KEY=your_key
STOCKFEED_TWELVEDATA_API_KEY=your_key
STOCKFEED_ALPACA_API_KEY=your_key
STOCKFEED_ALPACA_SECRET_KEY=your_secret
STOCKFEED_TRADIER_API_KEY=your_key
STOCKFEED_COINGECKO_API_KEY=your_key   # optional — free tier works without it

STOCKFEED_OPTIONS_RISK_FREE_RATE=0.05  # used for Black-Scholes greek calculation

STOCKFEED_CACHE_PATH=~/.stockfeed/cache.db
STOCKFEED_CACHE_ENABLED=true
STOCKFEED_LOG_LEVEL=INFO
STOCKFEED_LOG_FORMAT=console   # or "json"
```

Or configure programmatically:

```python
from stockfeed import StockFeedClient, StockFeedSettings

settings = StockFeedSettings(tiingo_api_key="...", cache_path="/tmp/sf.db")
client = StockFeedClient(settings=settings)
```

## Supported intervals

Both string values and the `Interval` enum are accepted everywhere:

| String | Enum | Description |
|---|---|---|
| `"1m"` | `Interval.ONE_MINUTE` | 1-minute bars |
| `"5m"` | `Interval.FIVE_MINUTES` | 5-minute bars |
| `"15m"` | `Interval.FIFTEEN_MINUTES` | 15-minute bars |
| `"30m"` | `Interval.THIRTY_MINUTES` | 30-minute bars |
| `"1h"` | `Interval.ONE_HOUR` | Hourly bars |
| `"4h"` | `Interval.FOUR_HOURS` | 4-hour bars |
| `"1d"` | `Interval.ONE_DAY` | Daily bars |
| `"1w"` | `Interval.ONE_WEEK` | Weekly bars |
| `"1mo"` | `Interval.ONE_MONTH` | Monthly bars |

## Provider support matrix

| Provider | OHLCV | Quote | Ticker info | Health | Expirations | Chain | Option quote | Greeks | Auth required |
|---|---|---|---|---|---|---|---|---|---|
| `yfinance` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Calculated (BS) | No |
| `tiingo` | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | — | Yes |
| `finnhub` | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | Calculated (BS) | Yes |
| `twelvedata` | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | — | Yes |
| `alpaca` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | API greeks | Yes |
| `tradier` | ✅ | ✅ | via yfinance | ✅ | ✅ | ✅ | ✅ | API greeks | Yes |
| `coingecko` | 🔜 | 🔜 | 🔜 | 🔜 | ❌ | ❌ | ❌ | — | Optional |

Providers without API keys configured are skipped during auto-selection. `yfinance` is always the final fallback.

List all registered providers at runtime:

```python
client = StockFeedClient()
for p in client.list_providers():
    print(p.name, "— auth required:", p.requires_auth)
```

## Error handling

All exceptions inherit from `StockFeedError` and carry structured context fields:

```python
from stockfeed.exceptions import TickerNotFoundError, ProviderUnavailableError

try:
    bars = client.get_ohlcv("INVALID", "1d", "2024-01-01", "2024-01-31")
except TickerNotFoundError as e:
    print(e.ticker, e.provider, e.suggestion)
except ProviderUnavailableError as e:
    print(f"Provider {e.provider} is down")
```

| Exception | When raised |
|---|---|
| `ProviderAuthError` | Missing or invalid API key |
| `ProviderRateLimitError` | Rate limit exceeded (`.retry_after` seconds) |
| `ProviderUnavailableError` | Provider unreachable or server error |
| `TickerNotFoundError` | Ticker doesn't exist on this provider |
| `UnsupportedIntervalError` | Interval not supported by provider |
| `CacheReadError` / `CacheWriteError` | DuckDB cache I/O failure |
| `ValidationError` | Bad input (ticker format, date range, etc.) |
| `ConfigurationError` | Missing or invalid configuration |
| `DevModeError` | Dev-only feature called outside dev mode |

## Examples

Working examples are in [`examples/`](examples/):

| File | What it shows |
|---|---|
| `01_ohlcv_yfinance.py` | Daily OHLCV bars with yfinance (no key needed) |
| `02_quote_and_ticker_info.py` | Live quote and company info |
| `03_cache.py` | Cache-first access — miss, write, hit, stats |
| `04_provider_health.py` | Registry inspection and health check |
| `05_async.py` | Concurrent fetching with `asyncio.gather` |
| `06_paid_provider.py` | Tiingo with auth and error handling |

## Development

```bash
git clone https://github.com/fuzzyalej/stockfeed
cd stockfeed
uv sync
```

Run checks:

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
uv run pytest --cov=stockfeed --cov-fail-under=90
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding new providers.

## License

MIT — see [LICENSE](LICENSE).
