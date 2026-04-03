# Tiingo

REST API: `https://api.tiingo.com` — [Get a free API key](https://api.tiingo.com)

## Setup

```env
STOCKFEED_TIINGO_API_KEY=your_key
```

Or programmatically:

```python
from stockfeed import StockFeedSettings
settings = StockFeedSettings(tiingo_api_key="your_key")
```

## Supported intervals

Daily/weekly/monthly: `1d`, `1w`, `1mo`

Intraday (via IEX endpoint): `1m`, `5m`, `15m`, `30m`, `1h`, `4h`

## Rate limits

Tiingo tracks rate limits via response headers (`X-RateLimit-Remaining`, `X-RateLimit-Reset`). `stockfeed` reads these headers automatically and marks the provider unavailable when the limit is reached.

Free tier: 500 requests/day, 50 requests/hour.

## Authentication

Uses `Authorization: Token <key>` header. A `ProviderAuthError` is raised on HTTP 401.

## Known limitations

- Intraday data requires IEX exchange data; some tickers may have limited intraday coverage
- `close_adj` is populated for daily bars; may be `None` for intraday
