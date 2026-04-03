# Providers overview

`stockfeed` abstracts multiple market data providers behind a single interface. When you call `get_ohlcv()`, the library automatically selects the best available provider, handles failures, and falls back transparently.

## Provider support matrix

| Provider | OHLCV | Quote | Ticker info | Health | Auth required |
|---|---|---|---|---|---|
| `yfinance` | ✅ | ✅ | ✅ | ✅ | No |
| `tiingo` | ✅ | ✅ | ✅ | ✅ | Yes — [free tier](https://api.tiingo.com) |
| `finnhub` | ✅ | ✅ | ✅ | ✅ | Yes — [free tier](https://finnhub.io) |
| `twelvedata` | ✅ | ✅ | ✅ | ✅ | Yes — [free tier](https://twelvedata.com) |
| `alpaca` | ✅ | ✅ | ✅ | ✅ | Yes — [paper accounts free](https://alpaca.markets) |
| `tradier` | ✅ | ✅ | via yfinance | ✅ | Yes |
| `coingecko` | 🔜 | 🔜 | 🔜 | 🔜 | Optional |

## Selection order

When `provider=None` (the default), the library selects providers in this order:

1. **Auth-configured providers** that are not rate-limited and support the requested interval, sorted by most-recently-healthy first
2. **`yfinance`** — always last, unconditional fallback

When `provider="tiingo"` is specified, that provider is tried first, then `yfinance` if it fails.

## Checking registered providers

```python
from stockfeed import StockFeedClient

client = StockFeedClient()
for p in client.list_providers():
    print(f"{p.name:12} requires_auth={p.requires_auth}")
    print(f"             intervals={[i.value for i in p.supported_intervals]}")
```

## Health checks

```python
health = client.health_check()
for name, status in health.items():
    print(name, "✅" if status.healthy else "❌", f"{status.latency_ms:.0f}ms")
```

Or check a single provider:

```python
status = client.health_check(provider="tiingo")
```

## Adding a third-party provider

Providers can be registered via Python entry points without modifying `stockfeed`:

```toml
# in your provider package's pyproject.toml
[project.entry-points."stockfeed.providers"]
myprovider = "myprovider.provider:MyProvider"
```

`ProviderRegistry.discover_entry_points()` loads all registered entry points on startup. See [Contributing](../contributing.md) for the full checklist.
