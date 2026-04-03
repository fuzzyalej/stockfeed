"""Twelve Data provider — sync and async implementation."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

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
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo
from stockfeed.providers.base import AbstractProvider
from stockfeed.providers.twelvedata.normalizer import TwelvedataNormalizer

_BASE_URL = "https://api.twelvedata.com"

_INTERVAL_MAP: dict[Interval, str] = {
    Interval.ONE_MINUTE: "1min",
    Interval.FIVE_MINUTES: "5min",
    Interval.FIFTEEN_MINUTES: "15min",
    Interval.THIRTY_MINUTES: "30min",
    Interval.ONE_HOUR: "1h",
    Interval.FOUR_HOURS: "4h",
    Interval.ONE_DAY: "1day",
    Interval.ONE_WEEK: "1week",
    Interval.ONE_MONTH: "1month",
}


def _raise_for_status(
    resp: httpx.Response, provider: str = "twelvedata", ticker: str | None = None
) -> None:
    if resp.status_code == 401:
        raise ProviderAuthError(
            "Twelve Data authentication failed (HTTP 401)",
            provider=provider,
            ticker=ticker,
            suggestion="Check your Twelve Data API key.",
        )
    if resp.status_code == 404:
        raise TickerNotFoundError(
            f"Twelve Data returned 404 for {ticker}",
            provider=provider,
            ticker=ticker,
        )
    if resp.status_code == 429:
        raise ProviderRateLimitError(
            "Twelve Data rate limit exceeded",
            provider=provider,
            ticker=ticker,
            suggestion="Wait before retrying or upgrade your Twelve Data plan.",
        )
    if resp.status_code >= 500:
        raise ProviderUnavailableError(
            f"Twelve Data server error (HTTP {resp.status_code})",
            provider=provider,
            ticker=ticker,
        )
    resp.raise_for_status()


class TwelvedataProvider(AbstractProvider):
    """Data provider backed by the Twelve Data REST API.

    Attributes
    ----------
    name : str
        ``"twelvedata"``
    supported_intervals : list[Interval]
        All :class:`Interval` values.
    requires_auth : bool
        ``True`` — a Twelve Data API key is required.
    """

    name = "twelvedata"
    supported_intervals = list(Interval)
    requires_auth = True

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key
        self._normalizer = TwelvedataNormalizer()

    # ------------------------------------------------------------------
    # HTTP client helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=_BASE_URL, timeout=30.0)

    def _async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0)

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
                f"Twelve Data: unsupported interval {interval}",
                provider="twelvedata",
                ticker=ticker,
            )

        start_str = start.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end.strftime("%Y-%m-%d %H:%M:%S")

        with self._client() as client:
            resp = client.get(
                "/time_series",
                params={
                    "symbol": ticker,
                    "interval": td_interval,
                    "start_date": start_str,
                    "end_date": end_str,
                    "outputsize": 5000,
                    "apikey": self._api_key,
                },
            )
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()

        if data.get("status") == "error":
            raise TickerNotFoundError(
                f"Twelve Data error for {ticker}: {data.get('message', 'unknown error')}",
                provider="twelvedata",
                ticker=ticker,
            )

        return self._normalizer.normalize_ohlcv((data, ticker, interval))

    def get_quote(self, ticker: str) -> Quote:
        with self._client() as client:
            price_resp = client.get(
                "/price",
                params={"symbol": ticker, "apikey": self._api_key},
            )
            _raise_for_status(price_resp, ticker=ticker)
            price_data = price_resp.json()

            quote_resp = client.get(
                "/quote",
                params={"symbol": ticker, "apikey": self._api_key},
            )
            # Quote endpoint may fail for some symbols — tolerate errors
            quote_data: dict[str, object] = {}
            if quote_resp.status_code == 200:
                quote_data = quote_resp.json()
                if quote_data.get("status") == "error":
                    quote_data = {}

        return self._normalizer.normalize_quote((price_data, quote_data, ticker))

    def get_ticker_info(self, ticker: str) -> TickerInfo:
        with self._client() as client:
            resp = client.get(
                "/profile",
                params={"symbol": ticker, "apikey": self._api_key},
            )
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()

        if data.get("status") == "error":
            raise TickerNotFoundError(
                f"Twelve Data profile error for {ticker}: {data.get('message', 'unknown')}",
                provider="twelvedata",
                ticker=ticker,
            )

        return self._normalizer.normalize_ticker_info((data, ticker))

    def health_check(self) -> HealthStatus:
        start = time.monotonic()
        error: str | None = None
        healthy = False
        try:
            with self._client() as client:
                resp = client.get(
                    "/price",
                    params={"symbol": "AAPL", "apikey": self._api_key},
                )
            healthy = resp.status_code == 200
            if not healthy:
                error = f"HTTP {resp.status_code}"
        except Exception as exc:
            error = str(exc)
        latency_ms = (time.monotonic() - start) * 1000
        return HealthStatus(
            provider="twelvedata",
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
