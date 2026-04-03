"""stockfeed — Unified market data access for Python."""

__version__ = "0.1.0"

from stockfeed.async_client import AsyncStockFeedClient
from stockfeed.client import ProviderInfo, StockFeedClient
from stockfeed.config import StockFeedSettings
from stockfeed.exceptions import (
    CacheError,
    CacheReadError,
    CacheWriteError,
    ConfigurationError,
    DevModeError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    StockFeedError,
    TickerNotFoundError,
    UnsupportedIntervalError,
    ValidationError,
)
from stockfeed.models import (
    Interval,
    OHLCVBar,
    Quote,
    StockFeedResponse,
    TickerInfo,
)

__all__ = [
    "__version__",
    # Clients
    "StockFeedClient",
    "AsyncStockFeedClient",
    "ProviderInfo",
    # Config
    "StockFeedSettings",
    # Models
    "Interval",
    "OHLCVBar",
    "Quote",
    "StockFeedResponse",
    "TickerInfo",
    # Exceptions
    "StockFeedError",
    "ProviderError",
    "ProviderAuthError",
    "ProviderRateLimitError",
    "ProviderUnavailableError",
    "TickerNotFoundError",
    "CacheError",
    "CacheReadError",
    "CacheWriteError",
    "ValidationError",
    "UnsupportedIntervalError",
    "ConfigurationError",
    "DevModeError",
]
