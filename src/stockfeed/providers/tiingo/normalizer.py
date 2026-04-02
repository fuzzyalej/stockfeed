"""Tiingo → canonical model normalizer."""

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


def _parse_dt(val: str) -> datetime:
    """Parse an ISO-8601 string (with or without timezone) into UTC datetime."""
    s = val.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Plain date "YYYY-MM-DD"
        dt = datetime.strptime(val[:10], "%Y-%m-%d")
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class TiingoNormalizer(BaseNormalizer):
    """Normalize Tiingo REST responses into canonical models."""

    def normalize_ohlcv(self, raw: Any) -> list[OHLCVBar]:
        """Convert a tuple ``(data, ticker, interval)`` to a list of OHLCVBar.

        *data* is the parsed JSON list returned by Tiingo's daily or intraday
        price endpoints.
        """
        try:
            data, ticker, interval = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "TiingoNormalizer.normalize_ohlcv expects (data, ticker, interval)",
                provider="tiingo",
            ) from exc

        if not data:
            raise ValidationError(
                f"Tiingo returned no OHLCV data for {ticker}",
                provider="tiingo",
                ticker=ticker,
                suggestion="Check that the ticker exists and the date range is valid.",
            )

        bars: list[OHLCVBar] = []
        for row in data:
            dt = _parse_dt(str(row["date"]))
            close_adj_val = _dec(row.get("adjClose"))
            bars.append(
                OHLCVBar(
                    ticker=ticker.upper(),
                    timestamp=dt,
                    interval=interval,
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close_raw=Decimal(str(row["close"])),
                    close_adj=close_adj_val,
                    volume=int(row["volume"]),
                    vwap=None,
                    trade_count=None,
                    provider="tiingo",
                )
            )

        return sorted(bars, key=lambda b: b.timestamp)

    def normalize_quote(self, raw: Any) -> Quote:
        """Convert a tuple ``(data, ticker)`` to a Quote.

        *data* is the first element from the Tiingo IEX endpoint list.
        """
        try:
            data, ticker = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "TiingoNormalizer.normalize_quote expects (data, ticker)",
                provider="tiingo",
            ) from exc

        if not data:
            raise ValidationError(
                f"Tiingo returned empty quote data for {ticker}",
                provider="tiingo",
                ticker=ticker,
            )

        last_val = _dec(data.get("last")) or Decimal("0")

        return Quote(
            ticker=ticker.upper(),
            timestamp=datetime.now(timezone.utc),
            bid=_dec(data.get("bidPrice")),
            ask=_dec(data.get("askPrice")),
            bid_size=data.get("bidSize"),
            ask_size=data.get("askSize"),
            last=last_val,
            last_size=None,
            volume=data.get("volume"),
            open=_dec(data.get("open")),
            high=_dec(data.get("high")),
            low=_dec(data.get("low")),
            close=_dec(data.get("prevClose")),
            change=None,
            change_pct=None,
            provider="tiingo",
        )

    def normalize_ticker_info(self, raw: Any) -> TickerInfo:
        """Convert a tuple ``(data, ticker)`` to a TickerInfo.

        *data* is the JSON dict from ``GET /tiingo/daily/{ticker}``.
        """
        try:
            data, ticker = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "TiingoNormalizer.normalize_ticker_info expects (data, ticker)",
                provider="tiingo",
            ) from exc

        if not data:
            raise ValidationError(
                f"Tiingo returned empty info for {ticker}",
                provider="tiingo",
                ticker=ticker,
            )

        return TickerInfo(
            ticker=ticker.upper(),
            name=data.get("name") or ticker,
            exchange=data.get("exchangeCode") or "UNKNOWN",
            currency=data.get("currency") or "USD",
            country=None,
            sector=None,
            industry=None,
            market_cap=None,
            provider="tiingo",
        )
