# Architecture Overview

## Design principles

- **Unified API** — every provider returns the same canonical models regardless of source
- **Cache-first** — DuckDB is checked before any network call; fetched data is written back automatically
- **Transparent failover** — providers are tried in order; yfinance is always the final fallback
- **Dual interface** — sync and async clients have identical method surfaces; async methods use `asyncio.to_thread` for providers that don't natively support async
- **Ergonomic inputs** — dates accept `"YYYY-MM-DD"` strings (UTC midnight) or `datetime`; intervals accept `"1d"` strings or `Interval` enum members

---

## Layer diagram

```
┌──────────────────────────────────────────┐
│  StockFeedClient / AsyncStockFeedClient  │  ← public API
└─────────────────────┬────────────────────┘
                      │
         ┌────────────▼────────────┐
         │    ProviderSelector     │  selects provider chain for each request
         └────────────┬────────────┘
                      │ ordered list of AbstractProvider
         ┌────────────▼────────────┐
         │     CacheManager        │  read → miss → fetch → write
         └────────────┬────────────┘
                      │
     ┌────────────────▼────────────────┐
     │  Provider (yfinance / tiingo / …)│  fetches raw data
     └────────────────┬────────────────┘
                      │ raw response (DataFrame / dict / JSON)
     ┌────────────────▼────────────────┐
     │     Normalizer                  │  maps to canonical models
     └─────────────────────────────────┘
```

---

## Package layout

```
src/stockfeed/
├── __init__.py              # public re-exports
├── client.py                # StockFeedClient (sync) — includes ProviderInfo dataclass
├── async_client.py          # AsyncStockFeedClient
├── _utils.py                # parse_dt / parse_interval helpers (internal)
├── config.py                # StockFeedSettings (pydantic-settings)
├── exceptions.py            # full exception hierarchy
├── logging.py               # structlog setup with correlation IDs
│
├── models/
│   ├── interval.py          # Interval enum (1m … 1mo)
│   ├── ohlcv.py             # OHLCVBar — close_raw + close_adj
│   ├── quote.py             # Quote — bid/ask/last snapshot
│   ├── ticker.py            # TickerInfo — exchange/sector/market_cap
│   ├── health.py            # HealthStatus — provider liveness snapshot
│   └── response.py          # StockFeedResponse[T] — generic envelope
│
├── normalizer/
│   └── base.py              # BaseNormalizer ABC
│
├── providers/
│   ├── base.py              # AbstractProvider ABC (sync + async)
│   ├── registry.py          # ProviderRegistry — register/get/discover
│   ├── selector.py          # ProviderSelector — builds ordered chain
│   ├── rate_limiter.py      # RateLimiter — DuckDB-backed per-provider state
│   ├── health.py            # HealthChecker — latency probes, history log
│   │
│   ├── yfinance/            # fully implemented
│   │   ├── provider.py
│   │   └── normalizer.py
│   │
│   ├── tiingo/              # fully implemented (OHLCV, quote, ticker_info, health)
│   ├── finnhub/             # fully implemented (OHLCV, quote, ticker_info, health)
│   ├── twelvedata/          # fully implemented (OHLCV, quote, ticker_info, health)
│   ├── alpaca/              # fully implemented (OHLCV, quote, ticker_info, health)
│   ├── tradier/             # fully implemented (OHLCV, quote, health; ticker_info via yfinance)
│   └── coingecko/           # scaffold only — methods raise NotImplementedError
│
├── cache/
│   ├── connection.py        # thread-safe DuckDB connection pool
│   └── schema.py            # DDL — ohlcv_bars, rate_limit_state, health_log
│
├── streaming/               # SSE streaming (planned)
└── dev/                     # dev/simulation mode (planned)
```

---

## Key models

### OHLCVBar

```python
class OHLCVBar(BaseModel):
    ticker: str
    timestamp: datetime          # always UTC
    interval: Interval
    open: Decimal
    high: Decimal
    low: Decimal
    close_raw: Decimal           # unadjusted close
    close_adj: Decimal | None    # split/dividend-adjusted close
    volume: int
    vwap: Decimal | None
    trade_count: int | None
    provider: str                # which provider served this bar
```

Both `close_raw` and `close_adj` are always exposed. For yfinance this is achieved by calling `history()` twice — once with `auto_adjust=False` and once with `auto_adjust=True`.

### Interval

```python
class Interval(str, Enum):
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1mo"
```

---

## Provider contract

Every provider implements `AbstractProvider`:

```python
class AbstractProvider(ABC):
    name: str                        # "yfinance", "tiingo", …
    supported_intervals: list[Interval]
    requires_auth: bool

    # sync
    def get_ohlcv(ticker, interval, start, end) -> list[OHLCVBar]: ...
    def get_quote(ticker) -> Quote: ...
    def get_ticker_info(ticker) -> TickerInfo: ...
    def health_check() -> HealthStatus: ...

    # async (mirrors above)
    async def async_get_ohlcv(...): ...
    async def async_get_quote(...): ...
    async def async_get_ticker_info(...): ...
    async def async_health_check(...): ...
```

Each provider has a paired `Normalizer` that converts the raw provider response (DataFrame, dict, JSON) into the canonical model. This keeps the provider class focused on I/O and the normalizer focused on data mapping.

---

## Provider selection

`ProviderSelector.select(ticker, interval, preferred=None)` returns an ordered list of providers:

1. **Preferred provider** (if specified and available)
2. **Auth'd providers** that are not rate-limited and support the interval, sorted by most-recently-healthy
3. **yfinance** — always last

The client iterates this list and returns the first successful response.

---

## Rate limiting

`RateLimiter` persists per-provider state to DuckDB (`rate_limit_state` table). State is updated from HTTP response headers:

| Header | Meaning |
|---|---|
| `X-RateLimit-Remaining` | Calls left in current window |
| `X-RateLimit-Limit` | Total calls per window |
| `X-RateLimit-Reset` | Window reset Unix timestamp |
| `Retry-After` | Seconds to wait after a 429 |

`is_available(provider)` returns `False` if the remaining count is 0 or a `Retry-After` window hasn't expired.

---

## Cache strategy

```
request(ticker, interval, start, end)
       │
       ▼
CacheManager.read(ticker, interval, start, end)
       │
   ┌───┴───────────────┐
   │ full hit           │ → return cached bars
   │ partial hit        │ → return cached bars + fetch missing ranges
   │ miss               │ → fetch all from provider
   └───────────────────┘
       │
       ▼
Provider.get_ohlcv(...)
       │
       ▼
CacheManager.write(bars)   ← upsert, no duplicates
       │
       ▼
return bars
```

Cache entries are market-hours aware: intraday bars during open market hours are never served from cache (they may be incomplete).

---

## Exception hierarchy

```
StockFeedError
├── ProviderError
│   ├── ProviderAuthError
│   ├── ProviderRateLimitError   (.retry_after: float | None)
│   ├── ProviderUnavailableError
│   └── TickerNotFoundError
├── CacheError
│   ├── CacheReadError
│   └── CacheWriteError
├── ValidationError
├── UnsupportedIntervalError
├── ConfigurationError
└── DevModeError
```

All exceptions carry optional `provider`, `ticker`, and `suggestion` fields for actionable error messages.

---

## Configuration

`StockFeedSettings` uses `pydantic-settings` with `STOCKFEED_` prefix. Settings can come from environment variables or a `.env` file.

| Setting | Default | Description |
|---|---|---|
| `tiingo_api_key` | `None` | Tiingo API key |
| `finnhub_api_key` | `None` | Finnhub API key |
| `twelvedata_api_key` | `None` | Twelve Data API key |
| `alpaca_api_key` | `None` | Alpaca API key |
| `alpaca_secret_key` | `None` | Alpaca secret |
| `tradier_api_key` | `None` | Tradier API key |
| `coingecko_api_key` | `None` | CoinGecko API key (optional) |
| `cache_path` | `~/.stockfeed/cache.db` | DuckDB file path |
| `cache_enabled` | `True` | Toggle caching |
| `dev_mode` | `False` | Enable dev/simulation mode |
| `log_level` | `"INFO"` | Log level |
| `log_format` | `"console"` | `"console"` or `"json"` |

---

## Adding a new provider (third-party plugin)

Providers can be registered via entry points without modifying the core package:

```toml
# in your provider package's pyproject.toml
[project.entry-points."stockfeed.providers"]
myprovider = "myprovider.provider:MyProvider"
```

`ProviderRegistry.discover_entry_points()` loads all registered entry points automatically on startup.
