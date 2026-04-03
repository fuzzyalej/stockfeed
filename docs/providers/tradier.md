# Tradier

REST API: `https://api.tradier.com/v1` — [Get a developer account](https://tradier.com)

## Setup

```env
STOCKFEED_TRADIER_API_KEY=your_key
```

## Supported intervals

Daily: `1d`, `1w`, `1mo`

Intraday: `1m`, `5m`, `15m`

## Authentication

Uses `Authorization: Bearer <key>` header. A `ProviderAuthError` is raised on HTTP 401.

## Ticker info

Tradier does not provide company metadata. When `get_ticker_info()` is called, `stockfeed` falls back to `yfinance` automatically to fulfil the request.

## Rate limits

Tradier tracks rate limits via response headers. `stockfeed` handles 429 responses and falls back to the next provider.

## Known limitations

- `close_adj` is not returned; field will be `None`
- Ticker info always falls back to yfinance (no Tradier company data endpoint)
- Options data (available via Tradier) is out of scope for the current release
