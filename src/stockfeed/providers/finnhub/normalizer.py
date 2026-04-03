"""Finnhub → canonical model normalizer."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from stockfeed.exceptions import ValidationError
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo
from stockfeed.normalizer.base import BaseNormalizer


def _dec(val: Any) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


class FinnhubNormalizer(BaseNormalizer):
    """Normalize Finnhub REST responses into canonical models."""

    def normalize_ohlcv(self, raw: Any) -> list[OHLCVBar]:
        """Convert a tuple ``(data, ticker, interval)`` to a list of OHLCVBar.

        *data* is the JSON dict from ``GET /stock/candles``.
        Keys: ``s``, ``t``, ``o``, ``h``, ``l``, ``c``, ``v``.
        """
        try:
            data, ticker, interval = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "FinnhubNormalizer.normalize_ohlcv expects (data, ticker, interval)",
                provider="finnhub",
            ) from exc

        if not data:
            raise ValidationError(
                f"Finnhub returned no OHLCV data for {ticker}",
                provider="finnhub",
                ticker=ticker,
            )

        # Validate required parallel arrays
        self._require(data, "t", "o", "h", "l", "c", "v", context="Finnhub candles")

        timestamps: list[int] = data["t"]
        opens: list[float] = data["o"]
        highs: list[float] = data["h"]
        lows: list[float] = data["l"]
        closes: list[float] = data["c"]
        volumes: list[float] = data["v"]

        bars: list[OHLCVBar] = []
        for ts, o, h, lo, c, v in zip(
            timestamps, opens, highs, lows, closes, volumes, strict=False
        ):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            bars.append(
                OHLCVBar(
                    ticker=ticker.upper(),
                    timestamp=dt,
                    interval=interval,
                    open=Decimal(str(o)),
                    high=Decimal(str(h)),
                    low=Decimal(str(lo)),
                    close_raw=Decimal(str(c)),
                    close_adj=None,
                    volume=int(v),
                    vwap=None,
                    trade_count=None,
                    provider="finnhub",
                )
            )

        return sorted(bars, key=lambda b: b.timestamp)

    def normalize_quote(self, raw: Any) -> Quote:
        """Convert a tuple ``(data, ticker)`` to a Quote.

        *data* is the JSON dict from ``GET /quote``.
        Keys: ``c`` (current), ``h``, ``l``, ``o``, ``pc`` (prev close).
        """
        try:
            data, ticker = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "FinnhubNormalizer.normalize_quote expects (data, ticker)",
                provider="finnhub",
            ) from exc

        if not data:
            raise ValidationError(
                f"Finnhub returned empty quote data for {ticker}",
                provider="finnhub",
                ticker=ticker,
            )

        last_val = _dec(data.get("c")) or Decimal("0")

        return Quote(
            ticker=ticker.upper(),
            timestamp=datetime.now(timezone.utc),
            bid=None,
            ask=None,
            bid_size=None,
            ask_size=None,
            last=last_val,
            last_size=None,
            volume=None,
            open=_dec(data.get("o")),
            high=_dec(data.get("h")),
            low=_dec(data.get("l")),
            close=_dec(data.get("pc")),
            change=None,
            change_pct=None,
            provider="finnhub",
        )

    def normalize_ticker_info(self, raw: Any) -> TickerInfo:
        """Convert a tuple ``(data, ticker)`` to a TickerInfo.

        *data* is the JSON dict from ``GET /stock/profile2``.
        Keys: ``name``, ``exchange``, ``currency``, ``country``, ``finnhubIndustry``.
        """
        try:
            data, ticker = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "FinnhubNormalizer.normalize_ticker_info expects (data, ticker)",
                provider="finnhub",
            ) from exc

        if not data:
            raise ValidationError(
                f"Finnhub returned empty profile for {ticker}",
                provider="finnhub",
                ticker=ticker,
            )

        return TickerInfo(
            ticker=ticker.upper(),
            name=data.get("name") or ticker,
            exchange=data.get("exchange") or "UNKNOWN",
            currency=data.get("currency") or "USD",
            country=data.get("country"),
            sector=None,
            industry=data.get("finnhubIndustry"),
            market_cap=None,
            provider="finnhub",
        )
