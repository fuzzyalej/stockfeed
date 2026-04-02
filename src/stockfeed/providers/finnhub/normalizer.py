"""Finnhub normalizer — scaffold (not yet implemented)."""

from typing import Any

from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo
from stockfeed.normalizer.base import BaseNormalizer

_MSG = "Finnhub support coming soon. Use provider=None for auto-selection."


class FinnhubNormalizer(BaseNormalizer):
    def normalize_ohlcv(self, raw: Any) -> list[OHLCVBar]:
        raise NotImplementedError(_MSG)

    def normalize_quote(self, raw: Any) -> Quote:
        raise NotImplementedError(_MSG)

    def normalize_ticker_info(self, raw: Any) -> TickerInfo:
        raise NotImplementedError(_MSG)
