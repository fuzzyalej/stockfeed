"""Tradier provider — sync and async implementation."""

from __future__ import annotations

import asyncio
import time
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx

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
from stockfeed.providers.base import AbstractProvider
from stockfeed.providers.base_options import AbstractOptionsProvider
from stockfeed.providers.tradier.normalizer import TradierNormalizer
from stockfeed.providers.tradier.options_normalizer import TradierOptionsNormalizer

_BASE_URL = "https://api.tradier.com"

# Tradier supports a subset of intervals
_INTERVAL_MAP: dict[Interval, str] = {
    Interval.ONE_MINUTE: "1min",
    Interval.FIVE_MINUTES: "5min",
    Interval.FIFTEEN_MINUTES: "15min",
    Interval.ONE_DAY: "daily",
    Interval.ONE_WEEK: "weekly",
    Interval.ONE_MONTH: "monthly",
}

_INTRADAY_INTERVALS = {Interval.ONE_MINUTE, Interval.FIVE_MINUTES, Interval.FIFTEEN_MINUTES}
_SUPPORTED = list(_INTERVAL_MAP.keys())


def _raise_for_status(
    resp: httpx.Response, provider: str = "tradier", ticker: str | None = None
) -> None:
    if resp.status_code == 401:
        raise ProviderAuthError(
            "Tradier authentication failed (HTTP 401)",
            provider=provider,
            ticker=ticker,
            suggestion="Check your Tradier API key.",
        )
    if resp.status_code == 404:
        raise TickerNotFoundError(
            f"Tradier returned 404 for {ticker}",
            provider=provider,
            ticker=ticker,
        )
    if resp.status_code == 429:
        raise ProviderRateLimitError(
            "Tradier rate limit exceeded",
            provider=provider,
            ticker=ticker,
            suggestion="Wait before retrying.",
        )
    if resp.status_code == 400:
        raise ProviderUnavailableError(
            "Tradier bad request (HTTP 400) — no market data for the requested range",
            provider=provider,
            ticker=ticker,
        )
    if resp.status_code >= 500:
        raise ProviderUnavailableError(
            f"Tradier server error (HTTP {resp.status_code})",
            provider=provider,
            ticker=ticker,
        )
    resp.raise_for_status()


class TradierProvider(AbstractProvider, AbstractOptionsProvider):
    """Data provider backed by the Tradier REST API.

    Attributes
    ----------
    name : str
        ``"tradier"``
    supported_intervals : list[Interval]
        ONE_MINUTE, FIVE_MINUTES, FIFTEEN_MINUTES, ONE_DAY, ONE_WEEK,
        ONE_MONTH.
    requires_auth : bool
        ``True`` — a Tradier API key (Bearer token) is required.

    Notes
    -----
    ``get_ticker_info`` is intentionally not supported; callers should use
    the yfinance provider for company metadata.
    """

    name = "tradier"
    supported_intervals = _SUPPORTED
    requires_auth = True

    def __init__(self, api_key: str = "", risk_free_rate: Decimal = Decimal("0.05")) -> None:
        self._api_key = api_key
        self._normalizer = TradierNormalizer()
        self._options_normalizer = TradierOptionsNormalizer(risk_free_rate=risk_free_rate)

    # ------------------------------------------------------------------
    # HTTP client helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=_BASE_URL,
            headers=self._headers(),
            timeout=30.0,
        )

    def _async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=_BASE_URL,
            headers=self._headers(),
            timeout=30.0,
        )

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
        td_interval = _INTERVAL_MAP.get(interval)
        if td_interval is None:
            raise ProviderUnavailableError(
                f"Tradier: unsupported interval {interval}",
                provider="tradier",
                ticker=ticker,
            )

        is_intraday = interval in _INTRADAY_INTERVALS

        with self._client() as client:
            if is_intraday:
                resp = client.get(
                    "/v1/markets/timesales",
                    params={
                        "symbol": ticker,
                        "interval": td_interval,
                        "start": start.strftime("%Y-%m-%d %H:%M"),
                        "end": end.strftime("%Y-%m-%d %H:%M"),
                    },
                )
            else:
                resp = client.get(
                    "/v1/markets/history",
                    params={
                        "symbol": ticker,
                        "interval": td_interval,
                        "start": start.strftime("%Y-%m-%d"),
                        "end": end.strftime("%Y-%m-%d"),
                    },
                )
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()

        return self._normalizer.normalize_ohlcv((data, ticker, interval, is_intraday))

    def get_quote(self, ticker: str) -> Quote:
        with self._client() as client:
            resp = client.get(
                "/v1/markets/quotes",
                params={"symbols": ticker},
            )
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()

        return self._normalizer.normalize_quote((data, ticker))

    def get_ticker_info(self, ticker: str) -> TickerInfo:
        raise NotImplementedError(
            "Tradier does not provide company info. Use yfinance for TickerInfo."
        )

    def health_check(self) -> HealthStatus:
        start = time.monotonic()
        error: str | None = None
        healthy = False
        try:
            with self._client() as client:
                resp = client.get("/v1/markets/clock")
            healthy = resp.status_code == 200
            if not healthy:
                error = f"HTTP {resp.status_code}"
        except Exception as exc:
            error = str(exc)
        latency_ms = (time.monotonic() - start) * 1000
        return HealthStatus(
            provider="tradier",
            healthy=healthy,
            latency_ms=latency_ms,
            error=error,
            checked_at=datetime.now(timezone.utc),
            rate_limit_remaining=None,
        )

    # ------------------------------------------------------------------
    # Async
    # ------------------------------------------------------------------

    async def async_get_ohlcv(
        self,
        ticker: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> list[OHLCVBar]:
        return await asyncio.to_thread(self.get_ohlcv, ticker, interval, start, end)

    async def async_get_quote(self, ticker: str) -> Quote:
        return await asyncio.to_thread(self.get_quote, ticker)

    async def async_get_ticker_info(self, ticker: str) -> TickerInfo:
        raise NotImplementedError(
            "Tradier does not provide company info. Use yfinance for TickerInfo."
        )

    async def async_health_check(self) -> HealthStatus:
        return await asyncio.to_thread(self.health_check)

    # ------------------------------------------------------------------
    # Options (sync)
    # ------------------------------------------------------------------

    def get_option_expirations(self, ticker: str) -> list[date]:
        """Return available expiration dates for *ticker*."""
        with self._client() as client:
            resp = client.get(
                "/v1/markets/options/expirations",
                params={"symbol": ticker},
            )
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()
        return self._options_normalizer.normalize_expirations(data)

    def get_options_chain(self, ticker: str, expiration: date) -> OptionChain:
        """Return options chain for *ticker* at *expiration* with greeks."""
        with self._client() as client:
            resp = client.get(
                "/v1/markets/options/chains",
                params={"symbol": ticker, "expiration": expiration.isoformat(), "greeks": "true"},
            )
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()
        return self._options_normalizer.normalize_chain(ticker, expiration, data)

    def get_option_quote(self, symbol: str) -> OptionQuote:
        """Return a live quote for the OCC option *symbol* with greeks."""
        with self._client() as client:
            resp = client.get(
                "/v1/markets/options/quotes",
                params={"symbols": symbol, "greeks": "true"},
            )
            _raise_for_status(resp, ticker=symbol)
            data = resp.json()
        return self._options_normalizer.normalize_option_quote(symbol, data)

    # ------------------------------------------------------------------
    # Options (async)
    # ------------------------------------------------------------------

    async def async_get_option_expirations(self, ticker: str) -> list[date]:
        """Async variant of :meth:`get_option_expirations`."""
        return await asyncio.to_thread(self.get_option_expirations, ticker)

    async def async_get_options_chain(self, ticker: str, expiration: date) -> OptionChain:
        """Async variant of :meth:`get_options_chain`."""
        return await asyncio.to_thread(self.get_options_chain, ticker, expiration)

    async def async_get_option_quote(self, symbol: str) -> OptionQuote:
        """Async variant of :meth:`get_option_quote`."""
        return await asyncio.to_thread(self.get_option_quote, symbol)
