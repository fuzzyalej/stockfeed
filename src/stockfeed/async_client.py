"""Asynchronous AsyncStockFeedClient — automatic provider selection with cache-first access."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import date, datetime

import stockfeed.providers as _providers_module  # noqa: F401 — triggers auto-registration
from stockfeed._utils import parse_dt, parse_interval
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
from stockfeed.models.options import OptionChain, OptionQuote
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo
from stockfeed.providers.health import HealthChecker
from stockfeed.providers.options_selector import OptionsProviderSelector
from stockfeed.providers.rate_limiter import RateLimiter
from stockfeed.providers.registry import get_default_registry
from stockfeed.providers.selector import ProviderSelector


class AsyncStockFeedClient:
    """Asynchronous client with automatic provider selection and cache-first access.

    Mirrors :class:`~stockfeed.client.StockFeedClient` exactly but exposes
    ``async def`` methods so callers can ``await`` them inside an event loop.

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
        *,
        dev_mode: bool = False,
    ) -> None:
        if settings is None:
            settings = StockFeedSettings()
        if dev_mode:
            settings = settings.model_copy(update={"dev_mode": True})
        self.settings = settings
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
        self._options_selector = OptionsProviderSelector(
            registry=get_default_registry(),
            rate_limiter=self._rate_limiter,
            health_checker=self._health_checker,
            settings=self.settings,
        )

    # ------------------------------------------------------------------
    # OHLCV
    # ------------------------------------------------------------------

    async def get_ohlcv(
        self,
        ticker: str,
        interval: str | Interval,
        start: str | datetime,
        end: str | datetime,
        provider: str | None = None,
    ) -> list[OHLCVBar]:
        """Async variant of :meth:`~stockfeed.client.StockFeedClient.get_ohlcv`.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.
        interval : str | Interval
            Bar width — ``"1d"``, ``"1h"``, etc., or an :class:`Interval` member.
        start : str | datetime
            Inclusive start. Accepts ``"YYYY-MM-DD"`` strings (parsed as UTC
            midnight) or a timezone-aware ``datetime``.
        end : str | datetime
            Exclusive end. Same format as *start*.
        provider : str | None
            Pin a specific provider by name. ``None`` means auto-select.
        """
        interval = parse_interval(interval)
        start = parse_dt(start)
        end = parse_dt(end)

        if self._cache and self._market_hours.should_use_cache(interval):
            cached = self._cache.read(ticker, interval, start, end)
            if cached is not None:
                return cached

        bars = await self._ohlcv_with_failover(ticker, interval, start, end, provider)

        if self._cache:
            self._cache.write(bars)

        return bars

    async def _ohlcv_with_failover(
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
                return await p.async_get_ohlcv(ticker, interval, start, end)
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

    async def get_quote(self, ticker: str, provider: str | None = None) -> Quote:
        """Async variant of :meth:`~stockfeed.client.StockFeedClient.get_quote`.

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
                return await p.async_get_quote(ticker)
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

    async def get_ticker_info(self, ticker: str, provider: str | None = None) -> TickerInfo:
        """Async variant of :meth:`~stockfeed.client.StockFeedClient.get_ticker_info`.

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
                return await p.async_get_ticker_info(ticker)
            except (ProviderRateLimitError, ProviderUnavailableError) as exc:
                last_exc = exc
            except (ProviderAuthError, TickerNotFoundError):
                raise
            except NotImplementedError:
                continue
        raise ProviderUnavailableError(
            f"All providers failed for {ticker}", ticker=ticker
        ) from last_exc

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self, provider: str | None = None) -> dict[str, HealthStatus]:
        """Async variant of :meth:`~stockfeed.client.StockFeedClient.health_check`.

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
                results[name] = await instance.async_health_check()
        return results

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------

    async def get_option_expirations(self, ticker: str, provider: str | None = None) -> list[date]:
        """Async variant of :meth:`~stockfeed.client.StockFeedClient.get_option_expirations`.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol (underlying).
        provider : str | None
            Pin a specific options provider. ``None`` means auto-select.
        """
        last_exc: Exception | None = None
        for p in self._options_selector.select(preferred=provider):
            try:
                return await p.async_get_option_expirations(ticker)
            except (ProviderRateLimitError, ProviderUnavailableError) as exc:
                last_exc = exc
            except (ProviderAuthError, TickerNotFoundError):
                raise
            except NotImplementedError:
                continue
        raise ProviderUnavailableError(
            f"No options provider could return expirations for {ticker}", ticker=ticker
        ) from last_exc

    async def get_options_chain(
        self, ticker: str, expiration: date, provider: str | None = None
    ) -> OptionChain:
        """Async variant of :meth:`~stockfeed.client.StockFeedClient.get_options_chain`.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol (underlying).
        expiration : date
            Expiration date.
        provider : str | None
            Pin a specific options provider. ``None`` means auto-select.
        """
        last_exc: Exception | None = None
        for p in self._options_selector.select(preferred=provider):
            try:
                return await p.async_get_options_chain(ticker, expiration)
            except (ProviderRateLimitError, ProviderUnavailableError) as exc:
                last_exc = exc
            except (ProviderAuthError, TickerNotFoundError):
                raise
            except NotImplementedError:
                continue
        raise ProviderUnavailableError(
            f"No options provider could return chain for {ticker} {expiration}", ticker=ticker
        ) from last_exc

    async def get_option_quote(self, symbol: str, provider: str | None = None) -> OptionQuote:
        """Async variant of :meth:`~stockfeed.client.StockFeedClient.get_option_quote`.

        Parameters
        ----------
        symbol : str
            OCC option symbol (e.g. ``"AAPL240119C00150000"``).
        provider : str | None
            Pin a specific options provider. ``None`` means auto-select.
        """
        last_exc: Exception | None = None
        for p in self._options_selector.select(preferred=provider):
            try:
                return await p.async_get_option_quote(symbol)
            except (ProviderRateLimitError, ProviderUnavailableError) as exc:
                last_exc = exc
            except (ProviderAuthError, TickerNotFoundError):
                raise
            except NotImplementedError:
                continue
        raise ProviderUnavailableError(
            f"No options provider could return quote for {symbol}"
        ) from last_exc

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def stream_quote(
        self,
        ticker: str,
        *,
        interval: float = 5.0,
        provider: str | None = None,
        max_errors: int = 5,
    ) -> AsyncGenerator[Quote, None]:
        """Stream live quotes by polling *ticker* every *interval* seconds.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.
        interval : float
            Seconds between polls. Defaults to ``5.0``.
        provider : str | None
            Pin a specific provider. ``None`` means auto-select.
        max_errors : int
            Maximum consecutive transient errors before aborting.

        Yields
        ------
        Quote
        """
        from stockfeed.streaming.sse import stream_quote as _stream_quote

        async for quote in _stream_quote(
            ticker, self, interval=interval, provider=provider, max_errors=max_errors
        ):
            yield quote

    # ------------------------------------------------------------------
    # Dev / simulation
    # ------------------------------------------------------------------

    async def simulate(
        self,
        ticker: str,
        start: str | datetime,
        end: str | datetime,
        interval: str | Interval,
        *,
        speed: float = 1.0,
    ) -> AsyncGenerator[OHLCVBar, None]:
        """Replay historical bars as an async stream (dev/backtest mode).

        Requires :attr:`~stockfeed.config.StockFeedSettings.dev_mode` to be
        ``True`` (or pass ``dev_mode=True`` to the client constructor).

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.
        start : str | datetime
            Inclusive start date. ``"YYYY-MM-DD"`` strings are accepted.
        end : str | datetime
            Exclusive end date.
        interval : str | Interval
            Bar width — ``"1d"``, ``"1h"``, etc.
        speed : float
            Playback multiplier. ``1.0`` replays in real time; ``0`` skips all
            sleeps (instant replay). Defaults to ``1.0``.

        Yields
        ------
        OHLCVBar
        """
        from stockfeed.dev.simulator import simulate as _simulate

        async for bar in _simulate(ticker, start, end, interval, speed=speed, client=self):
            yield bar
