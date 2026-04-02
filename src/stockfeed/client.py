"""Synchronous StockFeedClient — automatic provider selection with cache-first access."""

from __future__ import annotations

from datetime import datetime

import stockfeed.providers as _providers_module  # noqa: F401 — triggers auto-registration
from stockfeed.cache.manager import CacheManager
from stockfeed.cache.market_hours import MarketHoursChecker
from stockfeed.config import StockFeedSettings
from stockfeed.exceptions import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    TickerNotFoundError,
)
from stockfeed.models.health import HealthStatus
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo
from stockfeed.providers.health import HealthChecker
from stockfeed.providers.rate_limiter import RateLimiter
from stockfeed.providers.registry import get_default_registry
from stockfeed.providers.selector import ProviderSelector


class StockFeedClient:
    """Synchronous client with automatic provider selection and cache-first access.

    By default provider selection is automatic: yfinance is always available as a
    free fallback; paid providers (Tiingo, Finnhub, …) are used first when their
    API keys are configured. Pass ``provider="tiingo"`` to any method to pin a
    specific provider.

    Parameters
    ----------
    settings : StockFeedSettings | None
        Configuration (API keys, cache path, …). Reads from env / ``.env`` if
        not provided.
    db_path : str | None
        Override the DuckDB path. Defaults to ``settings.cache_path``.
    """

    def __init__(
        self,
        settings: StockFeedSettings | None = None,
        db_path: str | None = None,
    ) -> None:
        self.settings = settings or StockFeedSettings()
        self._db_path = db_path or self.settings.cache_path
        self._cache = CacheManager(db_path=self._db_path) if self.settings.cache_enabled else None
        self._rate_limiter = RateLimiter(db_path=self._db_path)
        self._health_checker = HealthChecker(db_path=self._db_path)
        self._market_hours = MarketHoursChecker()
        self._selector = ProviderSelector(
            registry=get_default_registry(),
            rate_limiter=self._rate_limiter,
            health_checker=self._health_checker,
            settings=self.settings,
        )

    # ------------------------------------------------------------------
    # OHLCV
    # ------------------------------------------------------------------

    def get_ohlcv(
        self,
        ticker: str,
        interval: Interval,
        start: datetime,
        end: datetime,
        provider: str | None = None,
    ) -> list[OHLCVBar]:
        """Return OHLCV bars for *ticker* over [start, end).

        Checks the cache first (skipped for intraday bars during open market hours).
        On a cache miss, tries providers in order until one succeeds, then caches
        the result. ``yfinance`` is always the final fallback.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.
        interval : Interval
            Bar width.
        start : datetime
            Inclusive start (UTC).
        end : datetime
            Exclusive end (UTC).
        provider : str | None
            Pin a specific provider by name (e.g. ``"tiingo"``). ``None`` means
            auto-select.
        """
        if self._cache and self._market_hours.should_use_cache(interval):
            cached = self._cache.read(ticker, interval, start, end)
            if cached is not None:
                return cached

        bars = self._ohlcv_with_failover(ticker, interval, start, end, provider)

        if self._cache:
            self._cache.write(bars)

        return bars

    def _ohlcv_with_failover(
        self,
        ticker: str,
        interval: Interval,
        start: datetime,
        end: datetime,
        preferred: str | None,
    ) -> list[OHLCVBar]:
        last_exc: Exception | None = None
        for p in self._selector.select(ticker, interval, preferred=preferred):
            try:
                return p.get_ohlcv(ticker, interval, start, end)
            except (ProviderRateLimitError, ProviderUnavailableError) as exc:
                last_exc = exc
            except (ProviderAuthError, TickerNotFoundError):
                raise
        raise ProviderUnavailableError(
            f"All providers failed for {ticker}", ticker=ticker
        ) from last_exc

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    def get_quote(self, ticker: str, provider: str | None = None) -> Quote:
        """Return the latest quote for *ticker* with automatic provider failover.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.
        provider : str | None
            Pin a provider by name. ``None`` means auto-select.
        """
        last_exc: Exception | None = None
        for p in self._selector.select(ticker, Interval.ONE_DAY, preferred=provider):
            try:
                return p.get_quote(ticker)
            except (ProviderRateLimitError, ProviderUnavailableError) as exc:
                last_exc = exc
            except (ProviderAuthError, TickerNotFoundError):
                raise
        raise ProviderUnavailableError(
            f"All providers failed for {ticker}", ticker=ticker
        ) from last_exc

    # ------------------------------------------------------------------
    # Ticker info
    # ------------------------------------------------------------------

    def get_ticker_info(self, ticker: str, provider: str | None = None) -> TickerInfo:
        """Return company/asset metadata for *ticker*.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.
        provider : str | None
            Pin a provider by name. ``None`` means auto-select.
        """
        last_exc: Exception | None = None
        for p in self._selector.select(ticker, Interval.ONE_DAY, preferred=provider):
            try:
                return p.get_ticker_info(ticker)
            except (ProviderRateLimitError, ProviderUnavailableError) as exc:
                last_exc = exc
            except (ProviderAuthError, TickerNotFoundError):
                raise
            except NotImplementedError:
                continue  # tradier and others don't support ticker_info
        raise ProviderUnavailableError(
            f"All providers failed for {ticker}", ticker=ticker
        ) from last_exc

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self, provider: str | None = None) -> dict[str, HealthStatus]:
        """Probe provider(s) and return health snapshots.

        Parameters
        ----------
        provider : str | None
            Check a single provider by name. ``None`` checks all registered providers.

        Returns
        -------
        dict[str, HealthStatus]
            Keyed by provider name.
        """
        registry = get_default_registry()
        targets = {provider: registry.get(provider)} if provider else registry.all()
        results: dict[str, HealthStatus] = {}
        for name, cls in targets.items():
            instance = self._selector._instantiate(cls)
            if instance is not None:
                results[name] = instance.health_check()
        return results
