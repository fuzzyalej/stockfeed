"""Alpaca provider — sync and async implementation."""

from __future__ import annotations

import asyncio
import re
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
from stockfeed.providers.alpaca.normalizer import AlpacaNormalizer
from stockfeed.providers.alpaca.options_normalizer import AlpacaOptionsNormalizer
from stockfeed.providers.base import AbstractProvider
from stockfeed.providers.base_options import AbstractOptionsProvider

_OCC_UNDERLYING_RE = re.compile(r"^([A-Z]+)\d{6}[CP]\d{8}$")

_BASE_URL = "https://data.alpaca.markets"

_TIMEFRAME_MAP: dict[Interval, str] = {
    Interval.ONE_MINUTE: "1Min",
    Interval.FIVE_MINUTES: "5Min",
    Interval.FIFTEEN_MINUTES: "15Min",
    Interval.THIRTY_MINUTES: "30Min",
    Interval.ONE_HOUR: "1Hour",
    Interval.FOUR_HOURS: "4Hour",
    Interval.ONE_DAY: "1Day",
    Interval.ONE_WEEK: "1Week",
    Interval.ONE_MONTH: "1Month",
}


def _raise_for_status(
    resp: httpx.Response, provider: str = "alpaca", ticker: str | None = None
) -> None:
    if resp.status_code in (401, 403):
        raise ProviderAuthError(
            f"Alpaca authentication failed (HTTP {resp.status_code})",
            provider=provider,
            ticker=ticker,
            suggestion="Check your Alpaca API key and secret.",
        )
    if resp.status_code in (404, 422):
        raise TickerNotFoundError(
            f"Alpaca returned {resp.status_code} for {ticker}",
            provider=provider,
            ticker=ticker,
        )
    if resp.status_code == 429:
        raise ProviderRateLimitError(
            "Alpaca rate limit exceeded",
            provider=provider,
            ticker=ticker,
            suggestion="Wait before retrying or upgrade your Alpaca plan.",
        )
    if resp.status_code >= 500:
        raise ProviderUnavailableError(
            f"Alpaca server error (HTTP {resp.status_code})",
            provider=provider,
            ticker=ticker,
        )
    resp.raise_for_status()


class AlpacaProvider(AbstractProvider, AbstractOptionsProvider):
    """Data provider backed by the Alpaca Markets Data API.

    Attributes
    ----------
    name : str
        ``"alpaca"``
    supported_intervals : list[Interval]
        All :class:`Interval` values.
    requires_auth : bool
        ``True`` — Alpaca API key and secret are required.
    """

    name = "alpaca"
    supported_intervals = list(_TIMEFRAME_MAP.keys())
    requires_auth = True

    def __init__(
        self,
        api_key: str = "",
        secret_key: str = "",
        risk_free_rate: Decimal = Decimal("0.05"),
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._risk_free_rate = risk_free_rate
        self._normalizer = AlpacaNormalizer()
        self._options_normalizer = AlpacaOptionsNormalizer(risk_free_rate=self._risk_free_rate)

    # ------------------------------------------------------------------
    # HTTP client helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._secret_key,
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
        timeframe = _TIMEFRAME_MAP.get(interval)
        if timeframe is None:
            raise ProviderUnavailableError(
                f"Alpaca: unsupported interval {interval}",
                provider="alpaca",
                ticker=ticker,
            )

        iso_start = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        iso_end = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        all_bars: list[dict[str, object]] = []
        params: dict[str, str | int] = {
            "timeframe": timeframe,
            "start": iso_start,
            "end": iso_end,
            "limit": 10000,
            "feed": "iex",
        }

        with self._client() as client:
            while True:
                resp = client.get(f"/v2/stocks/{ticker}/bars", params=params)
                _raise_for_status(resp, ticker=ticker)
                body = resp.json()
                bars = body.get("bars") or []
                all_bars.extend(bars)
                next_token = body.get("next_page_token")
                if not next_token:
                    break
                params = dict(params)
                params["page_token"] = next_token

        if not all_bars:
            raise TickerNotFoundError(
                f"Alpaca returned no bars for {ticker}",
                provider="alpaca",
                ticker=ticker,
            )

        return self._normalizer.normalize_ohlcv((all_bars, ticker, interval))

    def get_quote(self, ticker: str) -> Quote:
        with self._client() as client:
            q_resp = client.get(f"/v2/stocks/{ticker}/quotes/latest")
            _raise_for_status(q_resp, ticker=ticker)
            quote_data = q_resp.json()

            t_resp = client.get(f"/v2/stocks/{ticker}/trades/latest")
            _raise_for_status(t_resp, ticker=ticker)
            trade_data = t_resp.json()

        return self._normalizer.normalize_quote((quote_data, trade_data, ticker))

    def get_ticker_info(self, ticker: str) -> TickerInfo:
        with self._client() as client:
            resp = client.get(f"/v2/assets/{ticker}")
            _raise_for_status(resp, ticker=ticker)
            data = resp.json()

        return self._normalizer.normalize_ticker_info((data, ticker))

    def health_check(self) -> HealthStatus:
        start = time.monotonic()
        error: str | None = None
        healthy = False
        try:
            with self._client() as client:
                resp = client.get("/v2/stocks/AAPL/trades/latest")
            healthy = resp.status_code == 200
            if not healthy:
                error = f"HTTP {resp.status_code}"
        except Exception as exc:
            error = str(exc)
        latency_ms = (time.monotonic() - start) * 1000
        return HealthStatus(
            provider="alpaca",
            healthy=healthy,
            latency_ms=latency_ms,
            error=error,
            checked_at=datetime.now(timezone.utc),
            rate_limit_remaining=None,
        )

    # ------------------------------------------------------------------
    # Options — sync
    # ------------------------------------------------------------------

    def get_option_expirations(self, ticker: str) -> list[date]:
        """Return unique, sorted expiration dates available for *ticker*."""
        all_contracts: list[dict] = []
        params: dict[str, object] = {
            "underlying_symbols": ticker,
            "limit": 1000,
        }
        with self._client() as client:
            while True:
                resp = client.get("/v1beta1/options/contracts", params=params)
                _raise_for_status(resp, ticker=ticker)
                body = resp.json()
                all_contracts.extend(body.get("option_contracts") or [])
                next_token = body.get("next_page_token")
                if not next_token:
                    break
                params = dict(params)
                params["page_token"] = next_token
        return self._options_normalizer.normalize_expirations({"option_contracts": all_contracts})

    def get_options_chain(self, ticker: str, expiration: date) -> OptionChain:
        """Return all contracts for *ticker* at *expiration*."""
        merged_snapshots: dict[str, object] = {}
        params: dict[str, object] = {
            "expiration_date": expiration.isoformat(),
            "limit": 1000,
            "feed": "indicative",
        }
        with self._client() as client:
            while True:
                resp = client.get(f"/v1beta1/options/snapshots/{ticker}", params=params)
                _raise_for_status(resp, ticker=ticker)
                body = resp.json()
                snapshots = body.get("snapshots") or {}
                merged_snapshots.update(snapshots)
                next_token = body.get("next_page_token")
                if not next_token:
                    break
                params = dict(params)
                params["page_token"] = next_token
        return self._options_normalizer.normalize_chain(ticker, expiration, merged_snapshots)

    def get_option_quote(self, symbol: str) -> OptionQuote:
        """Return a live quote for the OCC option *symbol*."""
        m = _OCC_UNDERLYING_RE.match(symbol)
        if not m:
            raise ValueError(f"Cannot parse OCC symbol: {symbol!r}")
        underlying = m.group(1)
        params: dict[str, object] = {
            "symbols": symbol,
            "feed": "indicative",
        }
        with self._client() as client:
            resp = client.get(f"/v1beta1/options/snapshots/{underlying}", params=params)
            _raise_for_status(resp, ticker=underlying)
            body = resp.json()
        snapshots = body.get("snapshots") or {}
        snapshot = snapshots.get(symbol, {})
        return self._options_normalizer.normalize_option_quote(symbol, snapshot)

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
        return await asyncio.to_thread(self.get_option_expirations, ticker)

    async def async_get_options_chain(self, ticker: str, expiration: date) -> OptionChain:
        return await asyncio.to_thread(self.get_options_chain, ticker, expiration)

    async def async_get_option_quote(self, symbol: str) -> OptionQuote:
        return await asyncio.to_thread(self.get_option_quote, symbol)
