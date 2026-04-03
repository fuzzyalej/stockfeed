# Twelve Data

REST API: `https://api.twelvedata.com` — [Get a free API key](https://twelvedata.com)

## Setup

```env
STOCKFEED_TWELVEDATA_API_KEY=your_key
```

## Supported intervals

All intervals: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`, `1mo`.

Twelve Data is one of the few providers with native `4h` support.

## Rate limits

Free tier: 8 requests/minute, 800 requests/day. `stockfeed` reads `X-RateLimit-*` headers and handles 429 responses automatically.

## Authentication

Uses `apikey` query parameter. A `ProviderAuthError` is raised on HTTP 401.

## Known limitations

- Free tier has limited historical depth (some endpoints limited to 1 year)
- `close_adj` availability depends on the ticker and subscription tier
