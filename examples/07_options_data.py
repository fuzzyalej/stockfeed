"""Example 7 — Options data: expirations, chain, greeks, and single-contract quotes.

Uses yfinance (no API key required). For API-sourced greeks, configure a
Tradier or Alpaca key and pass provider="tradier" or provider="alpaca".

Run:
    python examples/07_options_data.py
"""

from stockfeed import StockFeedClient
from stockfeed.models.options import GreeksSource, OptionType

TICKER = "AAPL"

client = StockFeedClient()

# ── 1. List available expiration dates ───────────────────────────────────────
print(f"=== Option expirations for {TICKER} ===")
expirations = client.get_option_expirations(TICKER)
print(f"  Found {len(expirations)} expiration dates")
for exp in expirations[:5]:
    print(f"    {exp}")
if len(expirations) > 5:
    print(f"    … and {len(expirations) - 5} more")
print()

# ── 2. Fetch the full options chain for the nearest expiration ────────────────
nearest = expirations[0]
print(f"=== Options chain: {TICKER} expiring {nearest} ===")
chain = client.get_options_chain(TICKER, nearest)

calls = [c for c in chain.contracts if c.option_type == OptionType.CALL]
puts = [c for c in chain.contracts if c.option_type == OptionType.PUT]
print(f"  {len(calls)} calls, {len(puts)} puts  (provider: {chain.provider})")
print()

# Show the first 3 calls with greeks
print("  Top 3 calls:")
for contract in calls[:3]:
    g = contract.greeks
    if g and g.delta is not None:
        source_label = "API" if g.source == GreeksSource.API else "calc"
        greeks_str = (
            f"delta={g.delta:.3f}  gamma={g.gamma:.4f}  "
            f"theta={g.theta:.4f}  vega={g.vega:.4f}  [{source_label}]"
        )
    elif g:
        greeks_str = f"greeks at expiry (source: {g.source.value})"
    else:
        greeks_str = "greeks unavailable"

    iv_str = f"{float(contract.implied_volatility):.1%}" if contract.implied_volatility else "—"
    print(f"    {contract.symbol}")
    print(f"      strike={contract.strike}  IV={iv_str}")
    print(f"      bid={contract.bid}  ask={contract.ask}  OI={contract.open_interest}")
    print(f"      {greeks_str}")
print()

# ── 3. Quote a single contract ────────────────────────────────────────────────
if calls:
    symbol = calls[0].symbol
    print(f"=== Single contract quote: {symbol} ===")
    quote = client.get_option_quote(symbol)
    print(f"  Bid / Ask  : {quote.bid} / {quote.ask}")
    print(f"  Last       : {quote.last}")
    print(f"  Volume     : {quote.volume}")
    print(f"  Open int.  : {quote.open_interest}")
    iv_str = f"{float(quote.implied_volatility):.1%}" if quote.implied_volatility else "—"
    print(f"  IV         : {iv_str}")
    if quote.greeks:
        g = quote.greeks
        src = "API" if g.source == GreeksSource.API else "Black-Scholes"
        print(f"  Greeks ({src}):")
        print(f"    delta={g.delta}  gamma={g.gamma}")
        print(f"    theta={g.theta}  vega={g.vega}  rho={g.rho}")
    print(f"  Provider   : {quote.provider}")
    print(f"  At         : {quote.timestamp}")
