# Streaming

`stockfeed` supports live quote streaming via `AsyncStockFeedClient.stream_quote()`. The generator polls a provider at a configurable interval and yields `Quote` objects indefinitely.

## Basic usage

```python
import asyncio
from stockfeed import AsyncStockFeedClient

async def main():
    client = AsyncStockFeedClient()

    async for quote in client.stream_quote("AAPL", interval=5.0):
        print(f"{quote.ticker}  last={quote.last}  bid={quote.bid}  ask={quote.ask}")
        # Break when done:
        # break

asyncio.run(main())
```

## Parameters

```python
client.stream_quote(
    ticker: str,
    *,
    interval: float = 5.0,    # seconds between polls
    provider: str | None = None,  # pin a provider; None = auto-select
    max_errors: int = 5,      # consecutive errors before raising
)
```

## Error handling

| Error type | Behaviour |
|---|---|
| `ProviderAuthError` | Propagates immediately — stream terminates |
| `TickerNotFoundError` | Propagates immediately — stream terminates |
| `ProviderRateLimitError` | Retried up to `max_errors` times; uses `retry_after` if available |
| `ProviderUnavailableError` | Retried up to `max_errors` times; sleeps `interval` seconds |

After `max_errors` consecutive transient failures, the last exception propagates:

```python
from stockfeed.exceptions import ProviderUnavailableError

async for quote in client.stream_quote("AAPL", max_errors=3):
    try:
        process(quote)
    except ProviderUnavailableError:
        print("Provider down after 3 retries")
        break
```

## Collecting N quotes

```python
collected = []
async for quote in client.stream_quote("AAPL", interval=1.0):
    collected.append(quote)
    if len(collected) >= 10:
        break
```

## Pinning a provider

```python
async for quote in client.stream_quote("AAPL", provider="tiingo"):
    ...
```

## Under the hood

`stream_quote()` calls `client.get_quote()` in a loop and sleeps `interval` seconds between calls. It does not use WebSockets or true SSE — it is a polling-based generator. Native streaming from providers that support it is planned for a future release.
