"""Example 4 — Check provider health and registry.

Shows which providers are registered and probes yfinance liveness.
Providers that require auth will only be available if their API key
is set (STOCKFEED_TIINGO_API_KEY, etc.).

Run:
    python examples/04_provider_health.py
"""

import stockfeed.providers  # noqa: F401 — triggers auto-registration
from stockfeed.providers.registry import get_default_registry
from stockfeed.providers.yfinance.provider import YFinanceProvider

# --- Registry ---
registry = get_default_registry()
print("Registered providers:")
for p in registry.all().values():
    auth = "requires API key" if p.requires_auth else "no auth needed"
    intervals = ", ".join(i.value for i in p.supported_intervals[:4])
    print(f"  {p.name:<12} ({auth})  intervals: {intervals} ...")
print()

# --- Health check ---
provider = YFinanceProvider()
status = provider.health_check()
icon = "✓" if status.healthy else "✗"
latency = f"{status.latency_ms:.0f} ms" if status.latency_ms else "—"
print(f"Health check — yfinance")
print(f"  {icon} healthy  : {status.healthy}")
print(f"  latency  : {latency}")
if status.error:
    print(f"  error    : {status.error}")
