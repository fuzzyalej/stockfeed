# Alpaca

REST API: `https://data.alpaca.markets/v2` — [Create a free paper account](https://alpaca.markets)

## Setup

```env
STOCKFEED_ALPACA_API_KEY=your_key_id
STOCKFEED_ALPACA_SECRET_KEY=your_secret_key
```

## Supported intervals

All intervals: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`, `1mo`.

## Rate limits

Rate limits vary by subscription. `stockfeed` reads `X-RateLimit-*` headers and handles 429 responses.

## Authentication

Uses `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY` headers. A `ProviderAuthError` is raised on HTTP 403.

## Notes

- Alpaca specialises in US equities; international tickers may not be available
- Free paper accounts provide access to historical data
- `vwap` and `trade_count` are populated when available (intraday bars)

## Known limitations

- Crypto data is available but `stockfeed`'s CoinGecko provider is the planned crypto path
- `close_adj` is not returned by Alpaca; field will be `None`
