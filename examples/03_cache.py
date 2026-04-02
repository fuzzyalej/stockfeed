"""Example 3 — Cache-first data access.

First call fetches from yfinance and writes to DuckDB.
Second call reads from the cache — no network request.

Run:
    python examples/03_cache.py
"""

import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from stockfeed.cache.manager import CacheManager
from stockfeed.models.interval import Interval
from stockfeed.providers.yfinance.provider import YFinanceProvider

# Use a temp directory so DuckDB gets a fresh (non-existing) file path.
# In production, omit db_path to use the default ~/.stockfeed/cache.db
_tmpdir = tempfile.mkdtemp()
db_path = str(Path(_tmpdir) / "example_cache.db")

cache = CacheManager(db_path=db_path)
provider = YFinanceProvider()

ticker = "NVDA"
interval = Interval.ONE_DAY
start = datetime(2024, 1, 1, tzinfo=timezone.utc)
end = datetime(2024, 3, 31, tzinfo=timezone.utc)

# --- First call: cache miss ---
t0 = time.perf_counter()
cached = cache.read(ticker, interval, start, end)
if cached is None:
    print("Cache miss — fetching from provider...")
    bars = provider.get_ohlcv(ticker, interval, start, end)
    cache.write(bars)
    print(f"  Fetched and cached {len(bars)} bars in {(time.perf_counter() - t0)*1000:.0f} ms")
else:
    bars = cached

# --- Second call: cache hit ---
# Read back using the exact range of bars we stored to avoid weekend/holiday gaps
# fooling the coverage check.
bar_start = bars[0].timestamp
bar_end_exclusive = bars[-1].timestamp
t1 = time.perf_counter()
cached2 = cache.read(ticker, interval, bar_start, bar_end_exclusive)
elapsed = (time.perf_counter() - t1) * 1000

if cached2 is not None:
    print(f"Cache hit  — returned {len(cached2)} bars in {elapsed:.1f} ms (no network)")
else:
    print("Cache miss on second call (unexpected)")

# --- Stats ---
stats = cache.stats()
print(f"\nCache stats:")
print(f"  Rows    : {stats.row_count:,}")
print(f"  Size    : {stats.size_bytes / 1024:.1f} KB")
print(f"  Oldest  : {stats.oldest_entry}")
print(f"  Newest  : {stats.newest_entry}")
