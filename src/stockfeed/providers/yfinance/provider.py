"""yfinance provider — sync and async implementation."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import yfinance as yf

from stockfeed.exceptions import ProviderUnavailableError, TickerNotFoundError
from stockfeed.models.health import HealthStatus
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo
from stockfeed.providers.base import AbstractProvider
from stockfeed.providers.yfinance.normalizer import YFinanceNormalizer

# Map Interval enum values to yfinance interval strings
_INTERVAL_MAP: dict[Interval, str] = {
    Interval.ONE_MINUTE: "1m",
    Interval.FIVE_MINUTES: "5m",
    Interval.FIFTEEN_MINUTES: "15m",
    Interval.THIRTY_MINUTES: "30m",
    Interval.ONE_HOUR: "1h",
    Interval.FOUR_HOURS: "1h",  # yfinance has no 4h; use 1h as best approximation
    Interval.ONE_DAY: "1d",
    Interval.ONE_WEEK: "1wk",
    Interval.ONE_MONTH: "1mo",
}


class YFinanceProvider(AbstractProvider):
    """Data provider backed by the ``yfinance`` Python library.

    yfinance requires no API key and is always available as the
    unconditional fallback in the provider failover chain.

    Attributes
    ----------
    name : str
        ``"yfinance"``
    supported_intervals : list[Interval]
        All :class:`Interval` values.
    requires_auth : bool
        ``False`` — no API key needed.
    """

    name = "yfinance"
    supported_intervals = list(Interval)
    requires_auth = False

    def __init__(self) -> None:
        self._normalizer = YFinanceNormalizer()

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def get_ohlcv(
        self,
        ticker: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar]:
        """Fetch OHLCV bars from yfinance.

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

        Returns
        -------
        list[OHLCVBar]
        """
        yf_interval = _INTERVAL_MAP[interval]
        t = yf.Ticker(ticker)
        try:
            raw_df = t.history(
                start=start,
                end=end,
                interval=yf_interval,
                auto_adjust=False,
                actions=False,
            )
            adj_df = t.history(
                start=start,
                end=end,
                interval=yf_interval,
                auto_adjust=True,
                actions=False,
            )
        except Exception as exc:
            raise ProviderUnavailableError(
                f"yfinance failed for {ticker}: {exc}",
                provider="yfinance",
                ticker=ticker,
            ) from exc

        if raw_df.empty:
            raise TickerNotFoundError(
                f"yfinance returned no data for {ticker}",
                provider="yfinance",
                ticker=ticker,
                suggestion="Verify the ticker symbol is correct.",
            )

        return self._normalizer.normalize_ohlcv((raw_df, adj_df, ticker, interval))

    def get_quote(self, ticker: str) -> Quote:
        """Return the latest quote for *ticker*.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.
        """
        try:
            t = yf.Ticker(ticker)
            info = t.info
        except Exception as exc:
            raise ProviderUnavailableError(
                f"yfinance failed fetching quote for {ticker}: {exc}",
                provider="yfinance",
                ticker=ticker,
            ) from exc

        if not info:
            raise TickerNotFoundError(
                f"yfinance returned no info for {ticker}",
                provider="yfinance",
                ticker=ticker,
            )

        return self._normalizer.normalize_quote((info, ticker))

    def get_ticker_info(self, ticker: str) -> TickerInfo:
        """Return metadata for *ticker*.

        Parameters
        ----------
        ticker : str
            Uppercase ticker symbol.
        """
        try:
            t = yf.Ticker(ticker)
            info = t.info
        except Exception as exc:
            raise ProviderUnavailableError(
                f"yfinance failed fetching info for {ticker}: {exc}",
                provider="yfinance",
                ticker=ticker,
            ) from exc

        if not info:
            raise TickerNotFoundError(
                f"yfinance returned no info for {ticker}",
                provider="yfinance",
                ticker=ticker,
            )

        return self._normalizer.normalize_ticker_info((info, ticker))

    def health_check(self) -> HealthStatus:
        """Probe yfinance with a lightweight AAPL request."""
        start = time.monotonic()
        try:
            t = yf.Ticker("AAPL")
            info = t.fast_info
            healthy = bool(info)
            error = None
        except Exception as exc:
            healthy = False
            error = str(exc)
        latency_ms = (time.monotonic() - start) * 1000
        return HealthStatus(
            provider="yfinance",
            healthy=healthy,
            latency_ms=latency_ms,
            error=error,
            checked_at=datetime.now(timezone.utc),
            rate_limit_remaining=None,
        )

    # ------------------------------------------------------------------
    # Async (run sync methods in thread pool to avoid blocking event loop)
    # ------------------------------------------------------------------

    async def async_get_ohlcv(
        self,
        ticker: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar]:
        """Async variant — runs :meth:`get_ohlcv` in a thread executor."""
        return await asyncio.to_thread(self.get_ohlcv, ticker, interval, start, end)

    async def async_get_quote(self, ticker: str) -> Quote:
        """Async variant — runs :meth:`get_quote` in a thread executor."""
        return await asyncio.to_thread(self.get_quote, ticker)

    async def async_get_ticker_info(self, ticker: str) -> TickerInfo:
        """Async variant — runs :meth:`get_ticker_info` in a thread executor."""
        return await asyncio.to_thread(self.get_ticker_info, ticker)

    async def async_health_check(self) -> HealthStatus:
        """Async variant — runs :meth:`health_check` in a thread executor."""
        return await asyncio.to_thread(self.health_check)
