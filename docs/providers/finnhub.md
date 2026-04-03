# Finnhub

REST API: `https://finnhub.io/api/v1` — [Get a free API key](https://finnhub.io)

## Setup

```env
STOCKFEED_FINNHUB_API_KEY=your_key
```

## Supported intervals

Intraday: `1m`, `5m`, `15m`, `30m`, `1h`

Daily: `1d`

!!! note
    Finnhub does not support `4h`, `1w`, or `1mo` intervals. Requests for unsupported intervals raise `UnsupportedIntervalError`.

## Rate limits

Free tier: 60 API calls/minute. `stockfeed` tracks limits from response headers and falls back to the next provider when the limit is hit.

## Authentication

Uses `token` query parameter. A `ProviderAuthError` is raised on HTTP 403.

## Known limitations

- OHLCV history for US stocks is limited on the free tier
- `close_adj` is not available from Finnhub; `close_adj` will be `None`
