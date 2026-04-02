"""Provider package — registers all built-in providers on import."""

from stockfeed.providers.alpaca.provider import AlpacaProvider
from stockfeed.providers.base import AbstractProvider
from stockfeed.providers.coingecko.provider import CoingeckoProvider
from stockfeed.providers.finnhub.provider import FinnhubProvider
from stockfeed.providers.health import HealthChecker
from stockfeed.providers.rate_limiter import RateLimiter
from stockfeed.providers.registry import ProviderRegistry, get_default_registry
from stockfeed.providers.selector import ProviderSelector
from stockfeed.providers.tiingo.provider import TiingoProvider
from stockfeed.providers.tradier.provider import TradierProvider
from stockfeed.providers.twelvedata.provider import TwelvedataProvider
from stockfeed.providers.yfinance.provider import YFinanceProvider

# Register all built-in providers in the default registry
_registry = get_default_registry()
for _cls in [
    YFinanceProvider,
    TiingoProvider,
    FinnhubProvider,
    TwelvedataProvider,
    AlpacaProvider,
    TradierProvider,
    CoingeckoProvider,
]:
    _registry.register(_cls)  # type: ignore[type-abstract]

__all__ = [
    "AbstractProvider",
    "HealthChecker",
    "ProviderRegistry",
    "ProviderSelector",
    "RateLimiter",
    "get_default_registry",
]
