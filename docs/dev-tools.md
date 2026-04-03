# Dev Tools

## Dev simulator

The dev simulator replays historical bars as an async stream, mimicking real-time data. Use it for backtesting, algorithm development, and integration testing without hitting live APIs.

### Enable dev mode

```python
from stockfeed import AsyncStockFeedClient

client = AsyncStockFeedClient(dev_mode=True)
# or: AsyncStockFeedClient(settings=StockFeedSettings(dev_mode=True))
```

Without `dev_mode=True`, `simulate()` raises `DevModeError` immediately.

### Basic usage

```python
import asyncio
from stockfeed import AsyncStockFeedClient

async def main():
    client = AsyncStockFeedClient(dev_mode=True)

    async for bar in client.simulate(
        ticker="AAPL",
        start="2024-01-01",
        end="2024-01-31",
        interval="1d",
        speed=0,       # 0 = as fast as possible (no sleep between bars)
    ):
        print(bar.timestamp.date(), bar.close_raw)

asyncio.run(main())
```

### Speed control

| `speed` | Behaviour |
|---|---|
| `0` | Instant — no sleep between bars |
| `1.0` | Real time — sleeps `interval_seconds` between bars |
| `10.0` | 10× faster than real time |
| `0.5` | Half speed |

### Parameters

```python
client.simulate(
    ticker: str,
    start: str | datetime,   # "YYYY-MM-DD" or datetime
    end: str | datetime,
    interval: str | Interval, # "1d", "1h", Interval.ONE_DAY, etc.
    speed: float = 1.0,
)
```

### How it works

1. Calls `client.get_ohlcv()` to fetch (or serve from cache) the full bar range
2. Sorts bars by timestamp ascending
3. Yields each bar, sleeping `interval_seconds / speed` between yields (or skipping sleep when `speed=0`)

---

## Cache CLI

The cache CLI lets you inspect and manage the DuckDB cache without writing Python.

### Stats

```bash
python -m stockfeed.cache stats
```

Output example:
```
rows:          12,453
size_bytes:    2,097,152
oldest_bar:    2023-01-02T00:00:00+00:00
newest_bar:    2024-06-28T00:00:00+00:00
```

### Clear cache

```bash
# Clear everything
python -m stockfeed.cache clear

# Clear a specific ticker
python -m stockfeed.cache clear --ticker AAPL

# Clear a specific interval
python -m stockfeed.cache clear --interval 1m

# Clear bars older than a date
python -m stockfeed.cache clear --before 2023-01-01
```

Options can be combined: `--ticker AAPL --before 2023-01-01` clears only AAPL bars before 2023.

### Export

```bash
# Export to CSV
python -m stockfeed.cache export --format csv --output ./data/

# Export to Parquet
python -m stockfeed.cache export --format parquet --output ./data/
```

Each ticker/interval combination is written to a separate file.

### Inspect

```bash
python -m stockfeed.cache inspect --ticker AAPL --interval 1d
```

Prints cached rows in a human-readable table.

---

## Backtesting workflow

A typical backtesting workflow using `stockfeed`:

```python
import asyncio
from stockfeed import AsyncStockFeedClient

async def backtest(strategy):
    # 1. Fetch and cache all required data first (speed=0)
    client = AsyncStockFeedClient(dev_mode=True)

    async for bar in client.simulate("AAPL", "2023-01-01", "2024-01-01", "1d", speed=0):
        strategy.on_bar(bar)

    print(f"PnL: {strategy.pnl}")

asyncio.run(backtest(MyStrategy()))
```

On the first run, `simulate()` fetches from the provider and writes to cache. Subsequent runs are served entirely from the local DuckDB file.
