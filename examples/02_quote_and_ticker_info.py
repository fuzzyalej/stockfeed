"""Example 2 — Fetch a live quote and company info using StockFeedClient.

Run:
    python examples/02_quote_and_ticker_info.py
"""

from stockfeed import StockFeedClient

client = StockFeedClient()

# --- Quote ---
quote = client.get_quote("MSFT")
print("=== Quote: MSFT ===")
print(f"  Last   : {quote.last}")
print(f"  Bid    : {quote.bid}  (size: {quote.bid_size})")
print(f"  Ask    : {quote.ask}  (size: {quote.ask_size})")
print(f"  Volume : {quote.volume:,}" if quote.volume else "  Volume : —")
print(f"  At     : {quote.timestamp}")
print()

# --- Ticker info ---
info = client.get_ticker_info("MSFT")
print("=== Ticker Info: MSFT ===")
print(f"  Name       : {info.name}")
print(f"  Exchange   : {info.exchange}")
print(f"  Currency   : {info.currency}")
print(f"  Sector     : {info.sector}")
print(f"  Industry   : {info.industry}")
print(f"  Market cap : ${info.market_cap:,}" if info.market_cap else "  Market cap : —")
