"""Abstract base class for all stockfeed data providers."""

from abc import ABC, abstractmethod
from datetime import datetime

from stockfeed.models.health import HealthStatus
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo


class AbstractProvider(ABC):
    """Contract every stockfeed provider must satisfy.

    Providers expose both synchronous and asynchronous variants of each
    data-fetching method so callers can choose the execution model that
    fits their application without changing the provider.

    Attributes
    ----------
    name : str
        Short identifier used in logs and the provider registry (e.g. ``"tiingo"``).
    supported_intervals : list[Interval]
        Intervals this provider can return data for.
    requires_auth : bool
        Whether an API key is required to use this provider.
    """

    name: str
    supported_intervals: list[Interval]
    requires_auth: bool

    # ------------------------------------------------------------------
    # Sync interface
    # ------------------------------------------------------------------

    @abstractmethod
    def get_ohlcv(
        self,
        ticker: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar]:
        """Return OHLCV bars for *ticker* over [start, end).

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol (e.g. ``"AAPL"``).
        interval : Interval
            Bar width (e.g. ``Interval.ONE_DAY``).
        start : datetime
            Inclusive start timestamp (UTC).
        end : datetime
            Exclusive end timestamp (UTC).

        Returns
        -------
        list[OHLCVBar]
            Bars in ascending timestamp order.

        Raises
        ------
        ProviderAuthError
            If the API key is missing or invalid.
        ProviderRateLimitError
            If the rate limit has been exceeded.
        ProviderUnavailableError
            If the provider is unreachable or returns a server error.
        TickerNotFoundError
            If the ticker does not exist on this provider.
        UnsupportedIntervalError
            If *interval* is not in ``supported_intervals``.
        """

    @abstractmethod
    def get_quote(self, ticker: str) -> Quote:
        """Return the latest quote for *ticker*.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.

        Returns
        -------
        Quote
            Most recent bid/ask/last snapshot.

        Raises
        ------
        ProviderAuthError
            If the API key is missing or invalid.
        ProviderRateLimitError
            If the rate limit has been exceeded.
        ProviderUnavailableError
            If the provider is unreachable.
        TickerNotFoundError
            If the ticker does not exist on this provider.
        """

    @abstractmethod
    def get_ticker_info(self, ticker: str) -> TickerInfo:
        """Return metadata for *ticker*.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.

        Returns
        -------
        TickerInfo
            Exchange, currency, sector, market cap, etc.

        Raises
        ------
        ProviderAuthError
            If the API key is missing or invalid.
        TickerNotFoundError
            If the ticker does not exist on this provider.
        """

    @abstractmethod
    def health_check(self) -> HealthStatus:
        """Probe the provider and return a health snapshot.

        Returns
        -------
        HealthStatus
            Whether the provider is reachable and the measured latency.
        """

    # ------------------------------------------------------------------
    # Async interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def async_get_ohlcv(
        self,
        ticker: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar]:
        """Async variant of :meth:`get_ohlcv`."""

    @abstractmethod
    async def async_get_quote(self, ticker: str) -> Quote:
        """Async variant of :meth:`get_quote`."""

    @abstractmethod
    async def async_get_ticker_info(self, ticker: str) -> TickerInfo:
        """Async variant of :meth:`get_ticker_info`."""

    @abstractmethod
    async def async_health_check(self) -> HealthStatus:
        """Async variant of :meth:`health_check`."""
