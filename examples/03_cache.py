"""Example 3 — Cache-first data access.

StockFeedClient checks the DuckDB cache before making any network call.
The first call fetches from a provider and stores the result; the second
call returns the same bars directly from cache — no network request.

Run:
    python examples/03_cache.py
"""

import tempfile
import time
from pathlib import Path

from stockfeed import StockFeedClient

# Use a temp dir so we always get a cold cache for this demo.
# In production, omit db_path to use the default ~/.stockfeed/cache.db
_tmpdir = tempfile.mkdtemp()
db_path = str(Path(_tmpdir) / "example_cache.db")

client = StockFeedClient(db_path=db_path)

ticker = "NVDA"

# --- First call: cache miss — fetches from provider ---
t0 = time.perf_counter()
bars = client.get_ohlcv(ticker, "1d", "2024-01-01", "2024-03-31")
elapsed_first = (time.perf_counter() - t0) * 1000
print(f"First call  (network): {len(bars)} bars in {elapsed_first:.0f} ms")

# --- Second call: cache hit — DuckDB only, no network ---
t1 = time.perf_counter()
bars2 = client.get_ohlcv(ticker, "1d", "2024-01-01", "2024-03-31")
elapsed_second = (time.perf_counter() - t1) * 1000
print(f"Second call (cached) : {len(bars2)} bars in {elapsed_second:.1f} ms")

speedup = elapsed_first / elapsed_second if elapsed_second > 0 else float("inf")
print(f"\nCache was {speedup:.0f}x faster")

# --- Cache stats ---
stats = client._cache.stats()  # type: ignore[union-attr]
print("\nCache stats:")
print(f"  Rows    : {stats.row_count:,}")
print(f"  Size    : {stats.size_bytes / 1024:.1f} KB")
print(f"  Oldest  : {stats.oldest_entry}")
print(f"  Newest  : {stats.newest_entry}")
