"""Coingecko provider — scaffold (not yet implemented)."""

from __future__ import annotations

from datetime import datetime

from stockfeed.models.health import HealthStatus
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo
from stockfeed.providers.base import AbstractProvider

_MSG = "Coingecko support coming soon. Use provider=None for auto-selection."


class CoingeckoProvider(AbstractProvider):
    name = "coingecko"
    supported_intervals = list(Interval)
    requires_auth = True

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key

    def get_ohlcv(
        self, ticker: str, interval: Interval, start: datetime, end: datetime
    ) -> list[OHLCVBar]:
        raise NotImplementedError(_MSG)

    def get_quote(self, ticker: str) -> Quote:
        raise NotImplementedError(_MSG)

    def get_ticker_info(self, ticker: str) -> TickerInfo:
        raise NotImplementedError(_MSG)

    def health_check(self) -> HealthStatus:
        raise NotImplementedError(_MSG)

    async def async_get_ohlcv(
        self, ticker: str, interval: Interval, start: datetime, end: datetime
    ) -> list[OHLCVBar]:
        raise NotImplementedError(_MSG)

    async def async_get_quote(self, ticker: str) -> Quote:
        raise NotImplementedError(_MSG)

    async def async_get_ticker_info(self, ticker: str) -> TickerInfo:
        raise NotImplementedError(_MSG)

    async def async_health_check(self) -> HealthStatus:
        raise NotImplementedError(_MSG)
