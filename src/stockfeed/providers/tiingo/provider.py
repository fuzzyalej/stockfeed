"""Tiingo provider — sync and async implementation."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import httpx

from stockfeed.exceptions import (
    ProviderAuthError,
    ProviderUnavailableError,
    TickerNotFoundError,
)
from stockfeed.models.health import HealthStatus
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo
from stockfeed.providers.base import AbstractProvider
from stockfeed.providers.tiingo.normalizer import TiingoNormalizer

_BASE_URL = "https://api.tiingo.com"

# Intraday intervals require the IEX endpoint with a resample frequency
_INTRADAY_RESAMPLE: dict[Interval, str] = {
    Interval.ONE_MINUTE: "1min",
    Interval.FIVE_MINUTES: "5min",
    Interval.FIFTEEN_MINUTES: "15min",
    Interval.THIRTY_MINUTES: "30min",
    Interval.ONE_HOUR: "1hour",
    Interval.FOUR_HOURS: "4hour",
}

_DAILY_INTERVALS = {Interval.ONE_DAY, Interval.ONE_WEEK, Interval.ONE_MONTH}


def _raise_for_status(resp: httpx.Response, provider: str = "tiingo", ticker: str | None = None) -> None:
    """Map HTTP error codes to stockfeed exceptions."""
    if resp.status_code == 401:
        raise ProviderAuthError(
            "Tiingo authentication failed (HTTP 401)",
            provider=provider,
            ticker=ticker,
            suggestion="Check your Tiingo API key.",
        )
    if resp.status_code == 404:
        raise TickerNotFoundError(
            f"Tiingo returned 404 for {ticker}",
            provider=provider,
            ticker=ticker,
        )
    if resp.status_code >= 500:
        raise ProviderUnavailableError(
            f"Tiingo server error (HTTP {resp.status_code})",
            provider=provider,
            ticker=ticker,
        )
    resp.raise_for_status()


class TiingoProvider(AbstractProvider):
    """Data provider backed by the Tiingo REST API.

    Attributes
    ----------
    name : str
        ``"tiingo"``
    supported_intervals : list[Interval]
        All :class:`Interval` values.
    requires_auth : bool
        ``True`` — a Tiingo API key is required.
    """

    name = "tiingo"
    supported_intervals = list(Interval)
    requires_auth = True

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key
        self._normalizer = TiingoNormalizer()

    # ------------------------------------------------------------------
    # HTTP client helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=_BASE_URL,
            headers={
                "Authorization": f"Token {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "Authorization": f"Token {self._api_key}",
                "Content-Type": "application/json",
            },
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
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        with self._client() as client:
            if interval in _DAILY_INTERVALS:
                resp = client.get(
                    f"/tiingo/daily/{ticker}/prices",
                    params={"startDate": start_str, "endDate": end_str},
                )
                _raise_for_status(resp, ticker=ticker)
                data = resp.json()
            else:
                resample = _INTRADAY_RESAMPLE.get(interval)
                if resample is None:
                    raise ProviderUnavailableError(
                        f"Tiingo: unsupported interval {interval}",
                        provider="tiingo",
                        ticker=ticker,
                    )
                resp = client.get(
                    f"/iex/{ticker}/prices",
                    params={
                        "startDate": start_str,
                        "endDate": end_str,
                        "resampleFreq": resample,
                    },
                )
                _raise_for_status(resp, ticker=ticker)
                data = resp.json()

        if not data:
            raise TickerNotFoundError(
                f"Tiingo returned no data for {ticker}",
                provider="tiingo",
                ticker=ticker,
            )

        return self._normalizer.normalize_ohlcv((data, ticker, interval))

    def get_quote(self, ticker: str) -> Quote:
        with self._client() as client:
            resp = client.get(f"/iex/{ticker}")
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()

        if not data:
            raise TickerNotFoundError(
                f"Tiingo returned no quote data for {ticker}",
                provider="tiingo",
                ticker=ticker,
            )

        first = data[0] if isinstance(data, list) else data
        return self._normalizer.normalize_quote((first, ticker))

    def get_ticker_info(self, ticker: str) -> TickerInfo:
        with self._client() as client:
            resp = client.get(f"/tiingo/daily/{ticker}")
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()

        return self._normalizer.normalize_ticker_info((data, ticker))

    def health_check(self) -> HealthStatus:
        start = time.monotonic()
        error: str | None = None
        healthy = False
        try:
            with self._client() as client:
                resp = client.get("/api/test")
            healthy = resp.status_code == 200
            if not healthy:
                error = f"HTTP {resp.status_code}"
        except Exception as exc:
            error = str(exc)
        latency_ms = (time.monotonic() - start) * 1000
        return HealthStatus(
            provider="tiingo",
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
        return await asyncio.to_thread(self.get_ticker_info, ticker)

    async def async_health_check(self) -> HealthStatus:
        return await asyncio.to_thread(self.health_check)
