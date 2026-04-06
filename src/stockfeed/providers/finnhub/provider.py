"""Finnhub provider — sync and async implementation."""

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
from stockfeed.providers.finnhub.normalizer import FinnhubNormalizer
from stockfeed.providers.finnhub.options_normalizer import FinnhubOptionsNormalizer

_BASE_URL = "https://finnhub.io/api/v1"

_RESOLUTION_MAP: dict[Interval, str] = {
    Interval.ONE_MINUTE: "1",
    Interval.FIVE_MINUTES: "5",
    Interval.FIFTEEN_MINUTES: "15",
    Interval.THIRTY_MINUTES: "30",
    Interval.ONE_HOUR: "60",
    Interval.ONE_DAY: "D",
    Interval.ONE_WEEK: "W",
    Interval.ONE_MONTH: "M",
}

_SUPPORTED = list(_RESOLUTION_MAP.keys())


def _raise_for_status(
    resp: httpx.Response, provider: str = "finnhub", ticker: str | None = None
) -> None:
    if resp.status_code in (401, 403):
        raise ProviderAuthError(
            f"Finnhub authentication failed (HTTP {resp.status_code})",
            provider=provider,
            ticker=ticker,
            suggestion="Check your Finnhub API key.",
        )
    if resp.status_code == 404:
        raise TickerNotFoundError(
            f"Finnhub returned 404 for {ticker}",
            provider=provider,
            ticker=ticker,
        )
    if resp.status_code == 429:
        raise ProviderRateLimitError(
            "Finnhub rate limit exceeded",
            provider=provider,
            ticker=ticker,
            suggestion="Wait before retrying or upgrade your Finnhub plan.",
        )
    if resp.status_code >= 500:
        raise ProviderUnavailableError(
            f"Finnhub server error (HTTP {resp.status_code})",
            provider=provider,
            ticker=ticker,
        )
    resp.raise_for_status()


class FinnhubProvider(AbstractProvider, AbstractOptionsProvider):
    """Data provider backed by the Finnhub REST API.

    Attributes
    ----------
    name : str
        ``"finnhub"``
    supported_intervals : list[Interval]
        All intervals except FOUR_HOURS.
    requires_auth : bool
        ``True`` — a Finnhub API key is required.
    """

    name = "finnhub"
    supported_intervals = _SUPPORTED
    requires_auth = True

    def __init__(self, api_key: str = "", risk_free_rate: Decimal = Decimal("0.05")) -> None:
        self._api_key = api_key
        self._risk_free_rate = risk_free_rate
        self._normalizer = FinnhubNormalizer()
        self._options_normalizer = FinnhubOptionsNormalizer(risk_free_rate=self._risk_free_rate)

    # ------------------------------------------------------------------
    # HTTP client helpers
    # ------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=_BASE_URL, timeout=30.0)

    def _async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0)

    def _params(
        self, extra: dict[str, str | int | float] | None = None
    ) -> dict[str, str | int | float]:
        p: dict[str, str | int | float] = {"token": self._api_key}
        if extra:
            p.update(extra)
        return p

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
        resolution = _RESOLUTION_MAP.get(interval)
        if resolution is None:
            raise ProviderUnavailableError(
                f"Finnhub: unsupported interval {interval}",
                provider="finnhub",
                ticker=ticker,
            )

        unix_start = int(start.timestamp())
        unix_end = int(end.timestamp())

        with self._client() as client:
            resp = client.get(
                "/stock/candles",
                params=self._params(
                    {
                        "symbol": ticker,
                        "resolution": resolution,
                        "from": unix_start,
                        "to": unix_end,
                    }
                ),
            )
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()

        if data.get("s") == "no_data":
            raise TickerNotFoundError(
                f"Finnhub returned no_data for {ticker}",
                provider="finnhub",
                ticker=ticker,
            )

        return self._normalizer.normalize_ohlcv((data, ticker, interval))

    def get_quote(self, ticker: str) -> Quote:
        with self._client() as client:
            resp = client.get("/quote", params=self._params({"symbol": ticker}))
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()

        return self._normalizer.normalize_quote((data, ticker))

    def get_ticker_info(self, ticker: str) -> TickerInfo:
        with self._client() as client:
            resp = client.get("/stock/profile2", params=self._params({"symbol": ticker}))
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()

        if not data:
            raise TickerNotFoundError(
                f"Finnhub returned no profile for {ticker}",
                provider="finnhub",
                ticker=ticker,
            )

        return self._normalizer.normalize_ticker_info((data, ticker))

    def health_check(self) -> HealthStatus:
        start = time.monotonic()
        error: str | None = None
        healthy = False
        try:
            with self._client() as client:
                resp = client.get("/quote", params=self._params({"symbol": "AAPL"}))
            healthy = resp.status_code == 200
            if not healthy:
                error = f"HTTP {resp.status_code}"
        except Exception as exc:
            error = str(exc)
        latency_ms = (time.monotonic() - start) * 1000
        return HealthStatus(
            provider="finnhub",
            healthy=healthy,
            latency_ms=latency_ms,
            error=error,
            checked_at=datetime.now(timezone.utc),
            rate_limit_remaining=None,
        )

    # ------------------------------------------------------------------
    # Options (sync)
    # ------------------------------------------------------------------

    def get_option_expirations(self, ticker: str) -> list[date]:
        raise NotImplementedError("Finnhub does not provide an option expirations endpoint")

    def get_options_chain(self, ticker: str, expiration: date) -> OptionChain:
        with self._client() as client:
            quote_resp = client.get("/quote", params=self._params({"symbol": ticker}))
            _raise_for_status(quote_resp, ticker=ticker)
            quote_data = quote_resp.json()

            chain_resp = client.get("/stock/option-chain", params=self._params({"symbol": ticker}))
            _raise_for_status(chain_resp, ticker=ticker)
            chain_data = chain_resp.json()

        underlying_price: Decimal | None = None
        current_price = quote_data.get("c")
        if current_price is not None:
            try:
                p = float(current_price)
                if p > 0:
                    underlying_price = Decimal(str(p))
            except (TypeError, ValueError):
                pass

        return self._options_normalizer.normalize_chain(
            underlying=ticker,
            expiration=expiration,
            raw=chain_data,
            underlying_price=underlying_price,
        )

    def get_option_quote(self, symbol: str) -> OptionQuote:
        raise NotImplementedError("Finnhub does not provide an option quote endpoint")

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

    async def async_get_option_expirations(self, ticker: str) -> list[date]:
        raise NotImplementedError("Finnhub does not provide an option expirations endpoint")

    async def async_get_options_chain(self, ticker: str, expiration: date) -> OptionChain:
        return await asyncio.to_thread(self.get_options_chain, ticker, expiration)

    async def async_get_option_quote(self, symbol: str) -> OptionQuote:
        raise NotImplementedError("Finnhub does not provide an option quote endpoint")
