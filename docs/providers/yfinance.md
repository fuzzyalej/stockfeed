# yfinance

The `yfinance` provider requires no API key and is always the final fallback in the provider chain. It wraps the [`yfinance`](https://github.com/ranaroussi/yfinance) Python library directly (no HTTP calls from `stockfeed` itself).

## Setup

No configuration needed. `yfinance` is always registered and always available.

## Supported intervals

All intervals: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`, `1mo`.

!!! note
    yfinance has no native `4h` interval. `stockfeed` maps `4h` to `1h` as the closest available approximation.

## Adjusted vs raw prices

`yfinance` is the only provider that natively returns both adjusted and raw prices. `stockfeed` calls `history()` twice — once with `auto_adjust=False` (raw) and once with `auto_adjust=True` (adjusted) — and combines the results into `close_raw` and `close_adj`.

## Rate limits

`yfinance` has no official rate limit. Be polite — avoid hammering it in tight loops.

## Known limitations

- No intraday data beyond 60 days
- Some tickers may return empty DataFrames without an explicit error
- International exchange coverage varies
