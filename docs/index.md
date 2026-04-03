# stockfeed

**Unified market data access for Python — stocks, futures, options, and crypto.**

`stockfeed` gives you a single, fully-typed API to fetch OHLCV bars, live quotes, and company metadata from multiple providers. Provider failover, intelligent caching, and both sync and async interfaces are built in.

## Why stockfeed?

| Without stockfeed | With stockfeed |
|---|---|
| Different API for every provider | One API, any provider |
| Manually handle rate limits | Automatic failover |
| Re-fetch the same data repeatedly | DuckDB cache, zero setup |
| Write async wrappers yourself | `AsyncStockFeedClient` built in |
| Decode different response shapes | Canonical `OHLCVBar`, `Quote`, `TickerInfo` |

## Five-line quickstart

```python
from stockfeed import StockFeedClient

client = StockFeedClient()
bars = client.get_ohlcv("AAPL", "1d", "2024-01-01", "2024-01-31")
for bar in bars:
    print(bar.timestamp.date(), bar.close_raw)
```

No API key required — `yfinance` is always available as a free fallback.

## Install

```bash
pip install stockfeed
```

## Next steps

- [Getting Started](getting-started.md) — first OHLCV call, configure providers, understand responses
- [Configuration](configuration.md) — all settings, API keys, cache tuning
- [Providers](providers/overview.md) — which providers support what, and how to set them up
- [Streaming](streaming.md) — live quote streaming with `stream_quote()`
- [Dev Tools](dev-tools.md) — simulator, cache CLI, backtesting workflow
- [API Reference](api-reference/client.md) — full method signatures and docstrings
