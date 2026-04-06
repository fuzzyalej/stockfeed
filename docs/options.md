# Options data

`stockfeed` provides a unified interface for options market data: expiration calendars, full options chains, and per-contract quotes — all with greeks attached. Greeks come directly from the provider API where the provider supports them, or are calculated locally via Black-Scholes when they do not. Either way, the source is always labelled explicitly on every `Greeks` object.

## Expiration dates

Retrieve all available expiration dates for a ticker:

```python
from stockfeed import StockFeedClient

client = StockFeedClient()

expirations = client.get_option_expirations("AAPL")
print(expirations[:3])
# [datetime.date(2024, 1, 19), datetime.date(2024, 2, 16), datetime.date(2024, 3, 15)]
```

The method returns a sorted `list[date]`. Pass `provider="tradier"` (or any other supported provider) to pin a specific source.

## Options chain

Fetch all contracts for a given expiration:

```python
from stockfeed import StockFeedClient

client = StockFeedClient()
expirations = client.get_option_expirations("AAPL")

chain = client.get_options_chain("AAPL", expirations[0])
print(chain.underlying, chain.expiration, len(chain.contracts), "contracts")

for contract in chain.contracts[:5]:
    greeks_delta = contract.greeks.delta if contract.greeks else "—"
    print(
        contract.symbol,
        contract.option_type,
        contract.strike,
        greeks_delta,
    )
```

`chain.contracts` is a list of `OptionContract` objects sorted by strike. Each contract carries bid, ask, last, volume, open interest, implied volatility, and a `Greeks` object (or `None` if greeks could not be computed).

## Single-contract quote

Quote a specific contract by its OCC symbol:

```python
from stockfeed import StockFeedClient

client = StockFeedClient()

quote = client.get_option_quote("AAPL240119C00150000")
print(quote.bid, quote.ask, quote.implied_volatility)
if quote.greeks:
    print(
        f"delta={quote.greeks.delta}  "
        f"gamma={quote.greeks.gamma}  "
        f"source={quote.greeks.source}"
    )
```

`OptionQuote` also carries `timestamp`, `volume`, `open_interest`, `underlying`, and `provider`.

## Provider support

| Provider | Expirations | Chain | Quote | Greeks source |
|---|---|---|---|---|
| `yfinance` | Yes | Yes | Yes | Calculated (Black-Scholes) |
| `tradier` | Yes | Yes | Yes | API greeks |
| `alpaca` | Yes | Yes | Yes | API greeks |
| `finnhub` | No | Yes | No | Calculated (Black-Scholes) |

Providers not listed here do not support options data and will be skipped during automatic provider selection for options calls.

## Greeks — always explicitly labelled

Every `Greeks` object has a `source` field of type `GreeksSource`:

- `GreeksSource.API` — values were returned directly by the provider.
- `GreeksSource.CALCULATED` — values were computed locally from the contract's implied volatility using the Black-Scholes model.

The source is never ambiguous. You can always check `contract.greeks.source` to know how the values were derived.

```python
from stockfeed.models.options import GreeksSource

if contract.greeks and contract.greeks.source == GreeksSource.CALCULATED:
    print("These greeks were computed locally via Black-Scholes")
```

## Black-Scholes implementation notes

When greeks are calculated locally, the implementation:

- Uses only Python stdlib — no `scipy` or `numpy` dependency.
- Reports **theta per calendar day** (not per trading day).
- Reports **vega per 1% move in implied volatility** (not per unit).
- Uses the configured risk-free rate (see below).

All five greeks are produced: delta, gamma, theta, vega, and rho. Any field may be `None` if the calculation inputs are insufficient (e.g. missing implied volatility).

## Configuring the risk-free rate

The risk-free rate used for Black-Scholes calculations defaults to `0.05` (5%). Override it via environment variable:

```env
STOCKFEED_OPTIONS_RISK_FREE_RATE=0.04
```

Or programmatically:

```python
from decimal import Decimal
from stockfeed import StockFeedClient, StockFeedSettings

settings = StockFeedSettings(options_risk_free_rate=Decimal("0.04"))
client = StockFeedClient(settings=settings)
```

## Async usage

All three methods exist on `AsyncStockFeedClient` as coroutines with identical signatures:

```python
import asyncio
from stockfeed import AsyncStockFeedClient

async def main():
    client = AsyncStockFeedClient()

    expirations = await client.get_option_expirations("AAPL")
    chain = await client.get_options_chain("AAPL", expirations[0])
    quote = await client.get_option_quote("AAPL240119C00150000")

    print(len(chain.contracts), "contracts fetched")
    print(quote.bid, quote.ask)

asyncio.run(main())
```

Use `asyncio.gather` to fetch chains for multiple expirations or tickers concurrently.
