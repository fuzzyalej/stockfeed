"""Full exception hierarchy for stockfeed."""


class StockFeedError(Exception):
    """Base exception for all stockfeed errors."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        ticker: str | None = None,
        suggestion: str | None = None,
    ) -> None:
        self.message = message
        self.provider = provider
        self.ticker = ticker
        self.suggestion = suggestion
        super().__init__(message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.provider:
            parts.append(f"provider={self.provider}")
        if self.ticker:
            parts.append(f"ticker={self.ticker}")
        if self.suggestion:
            parts.append(f"suggestion={self.suggestion}")
        return " | ".join(parts)


class ProviderError(StockFeedError):
    """Raised when a provider encounters an error."""


class ProviderAuthError(ProviderError):
    """Invalid or missing API key."""


class ProviderRateLimitError(ProviderError):
    """Rate limit hit for a provider."""

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        ticker: str | None = None,
        suggestion: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, provider=provider, ticker=ticker, suggestion=suggestion)
        self.retry_after = retry_after


class ProviderUnavailableError(ProviderError):
    """Provider is down or timed out."""


class TickerNotFoundError(ProviderError):
    """Ticker doesn't exist on this provider."""


class CacheError(StockFeedError):
    """Raised when a cache operation fails."""


class CacheReadError(CacheError):
    """Raised when reading from cache fails."""


class CacheWriteError(CacheError):
    """Raised when writing to cache fails."""


class ValidationError(StockFeedError):
    """Bad user input (ticker format, date range, etc.)."""


class UnsupportedIntervalError(StockFeedError):
    """Provider doesn't support the requested interval."""


class ConfigurationError(StockFeedError):
    """Missing or invalid configuration."""


class DevModeError(StockFeedError):
    """Dev-only feature used in non-dev context."""
