# CoinGecko

!!! warning "Coming soon"
    CoinGecko support is planned for the crypto phase. All methods currently raise `NotImplementedError`.

    Track progress at [github.com/your-org/stockfeed](https://github.com/your-org/stockfeed).

## Planned setup

```env
STOCKFEED_COINGECKO_API_KEY=your_key   # optional — free tier works without it
```

## What's planned

- OHLCV bars for crypto pairs (BTC/USD, ETH/USD, etc.)
- Live quote data
- Coin metadata (market cap, circulating supply, etc.)
- Free tier available without an API key (rate-limited)
- Pro tier with higher limits via API key

## Current behaviour

```python
from stockfeed.providers.coingecko.provider import CoingeckoProvider

p = CoingeckoProvider()
p.get_ohlcv(...)  # raises NotImplementedError
```

Use `provider=None` (the default) to skip CoinGecko and fall back to `yfinance` for any request.
