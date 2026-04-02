"""Example 4 — Check provider health via StockFeedClient.

Shows which providers are registered and probes their liveness.
Providers that require auth will only appear if their API key is set
(STOCKFEED_TIINGO_API_KEY, etc.).

Run:
    python examples/04_provider_health.py
"""

import stockfeed.providers  # noqa: F401 — triggers auto-registration

from stockfeed import StockFeedClient
from stockfeed.providers.registry import get_default_registry

# --- Registry ---
registry = get_default_registry()
print("Registered providers:")
for p in registry.all().values():
    auth = "requires API key" if p.requires_auth else "no auth needed"
    intervals = ", ".join(i.value for i in p.supported_intervals[:4])
    print(f"  {p.name:<12} ({auth})  intervals: {intervals} ...")
print()

# --- Health check via client (checks all configured providers) ---
client = StockFeedClient()
results = client.health_check()

print("Health checks:")
for name, status in results.items():
    icon = "✓" if status.healthy else "✗"
    latency = f"{status.latency_ms:.0f} ms" if status.latency_ms else "—"
    print(f"  {icon} {name:<12} healthy={status.healthy}  latency={latency}", end="")
    if status.error:
        print(f"  error: {status.error}", end="")
    print()
