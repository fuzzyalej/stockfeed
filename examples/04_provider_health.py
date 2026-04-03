"""Example 4 — List providers and check their health via StockFeedClient.

Providers that require auth will appear in the list but health checks for
them will only succeed if their API key is set
(STOCKFEED_TIINGO_API_KEY, STOCKFEED_FINNHUB_API_KEY, etc.).

Run:
    python examples/04_provider_health.py
"""

from stockfeed import StockFeedClient

client = StockFeedClient()

# --- Registered providers ---
print("Registered providers:")
for p in client.list_providers():
    auth = "requires API key" if p.requires_auth else "no auth needed"
    intervals = ", ".join(i.value for i in p.supported_intervals[:4])
    print(f"  {p.name:<12} ({auth})  intervals: {intervals} ...")
print()

# --- Health check (probes all configured providers) ---
results = client.health_check()

print("Health checks:")
for name, status in results.items():
    icon = "✓" if status.healthy else "✗"
    latency = f"{status.latency_ms:.0f} ms" if status.latency_ms else "—"
    print(f"  {icon} {name:<12} healthy={status.healthy}  latency={latency}", end="")
    if status.error:
        print(f"  error: {status.error}", end="")
    print()
