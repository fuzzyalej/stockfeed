# Configuration

`stockfeed` uses `pydantic-settings` for configuration. All settings can be provided via:

1. Environment variables (prefix `STOCKFEED_`)
2. A `.env` file in the working directory
3. Explicit `StockFeedSettings` instantiation

## Full settings reference

| Setting | Env var | Default | Description |
|---|---|---|---|
| `tiingo_api_key` | `STOCKFEED_TIINGO_API_KEY` | `None` | Tiingo API key |
| `finnhub_api_key` | `STOCKFEED_FINNHUB_API_KEY` | `None` | Finnhub API key |
| `twelvedata_api_key` | `STOCKFEED_TWELVEDATA_API_KEY` | `None` | Twelve Data API key |
| `alpaca_api_key` | `STOCKFEED_ALPACA_API_KEY` | `None` | Alpaca API key ID |
| `alpaca_secret_key` | `STOCKFEED_ALPACA_SECRET_KEY` | `None` | Alpaca secret key |
| `tradier_api_key` | `STOCKFEED_TRADIER_API_KEY` | `None` | Tradier API key |
| `coingecko_api_key` | `STOCKFEED_COINGECKO_API_KEY` | `None` | CoinGecko API key (optional) |
| `cache_path` | `STOCKFEED_CACHE_PATH` | `~/.stockfeed/cache.db` | DuckDB file path |
| `cache_enabled` | `STOCKFEED_CACHE_ENABLED` | `True` | Enable/disable caching |
| `dev_mode` | `STOCKFEED_DEV_MODE` | `False` | Enable dev/simulator mode |
| `log_level` | `STOCKFEED_LOG_LEVEL` | `"INFO"` | Logging level |
| `log_format` | `STOCKFEED_LOG_FORMAT` | `"console"` | `"console"` or `"json"` |

## Environment variables

```bash
export STOCKFEED_TIINGO_API_KEY=your_key
export STOCKFEED_CACHE_PATH=/tmp/stockfeed.db
```

## .env file

Create a `.env` file in your project root:

```env
STOCKFEED_TIINGO_API_KEY=your_key
STOCKFEED_FINNHUB_API_KEY=your_key
STOCKFEED_CACHE_PATH=~/.stockfeed/cache.db
STOCKFEED_LOG_FORMAT=json
```

`stockfeed` loads `.env` automatically via `pydantic-settings`.

## Programmatic configuration

```python
from stockfeed import StockFeedClient, StockFeedSettings

settings = StockFeedSettings(
    tiingo_api_key="your_key",
    cache_path="/data/stockfeed.db",
    log_level="DEBUG",
)
client = StockFeedClient(settings=settings)
```

## Provider selection

Providers without a configured API key are automatically excluded from the selection chain. `yfinance` is always available as the final fallback regardless of configuration.

```python
# Only tiingo and yfinance are tried — no finnhub or twelvedata keys set
settings = StockFeedSettings(tiingo_api_key="your_key")
client = StockFeedClient(settings=settings)
```

## Cache configuration

The cache is a single DuckDB file. By default it lives at `~/.stockfeed/cache.db`:

```python
settings = StockFeedSettings(
    cache_path="/fast-disk/stockfeed.db",  # override path
    cache_enabled=True,                    # default
)
```

Disable caching entirely (all requests hit providers):

```python
settings = StockFeedSettings(cache_enabled=False)
```

## Logging

`stockfeed` uses `structlog`. The default `"console"` format is human-readable; switch to `"json"` for production/log aggregators:

```env
STOCKFEED_LOG_FORMAT=json
STOCKFEED_LOG_LEVEL=WARNING
```

Each log line includes `provider`, `ticker`, and `interval` bound fields plus a correlation ID for request tracing.
