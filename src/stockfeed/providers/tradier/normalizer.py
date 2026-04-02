"""Tradier → canonical model normalizer."""

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


def _parse_date(val: str) -> datetime:
    """Parse a ``YYYY-MM-DD`` date string into a UTC midnight datetime."""
    dt = datetime.strptime(val[:10], "%Y-%m-%d")
    return dt.replace(tzinfo=timezone.utc)


def _parse_dt(val: str) -> datetime:
    """Parse a ``YYYY-MM-DD HH:MM:SS`` or ISO-8601 string into UTC datetime."""
    val = val.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(val, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Fallback to fromisoformat
    s = val.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class TradierNormalizer(BaseNormalizer):
    """Normalize Tradier REST responses into canonical models."""

    def normalize_ohlcv(self, raw: Any) -> list[OHLCVBar]:
        """Convert a tuple ``(data, ticker, interval, is_intraday)`` to a list of OHLCVBar.

        For daily/weekly/monthly, *data* is the response from
        ``GET /v1/markets/history`` and has the shape
        ``{"history": {"day": [...]}}``

        For intraday, *data* is from ``GET /v1/markets/timesales`` and has
        ``{"series": {"data": [...]}}``.
        """
        try:
            data, ticker, interval, is_intraday = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "TradierNormalizer.normalize_ohlcv expects (data, ticker, interval, is_intraday)",
                provider="tradier",
            ) from exc

        if not data:
            raise ValidationError(
                f"Tradier returned no OHLCV data for {ticker}",
                provider="tradier",
                ticker=ticker,
            )

        bars: list[OHLCVBar] = []

        if is_intraday:
            series = data.get("series") or {}
            rows = series.get("data") or []
            if isinstance(rows, dict):
                # Single row returned as a dict rather than a list
                rows = [rows]
            if not rows:
                raise ValidationError(
                    f"Tradier returned empty intraday series for {ticker}",
                    provider="tradier",
                    ticker=ticker,
                )
            for row in rows:
                dt = _parse_dt(str(row["time"]))
                bars.append(
                    OHLCVBar(
                        ticker=ticker.upper(),
                        timestamp=dt,
                        interval=interval,
                        open=Decimal(str(row["open"])),
                        high=Decimal(str(row["high"])),
                        low=Decimal(str(row["low"])),
                        close_raw=Decimal(str(row["close"])),
                        close_adj=None,
                        volume=int(row["volume"]),
                        vwap=None,
                        trade_count=None,
                        provider="tradier",
                    )
                )
        else:
            history = data.get("history") or {}
            rows = history.get("day") or []
            if isinstance(rows, dict):
                rows = [rows]
            if not rows:
                raise ValidationError(
                    f"Tradier returned empty history for {ticker}",
                    provider="tradier",
                    ticker=ticker,
                )
            for row in rows:
                dt = _parse_date(str(row["date"]))
                bars.append(
                    OHLCVBar(
                        ticker=ticker.upper(),
                        timestamp=dt,
                        interval=interval,
                        open=Decimal(str(row["open"])),
                        high=Decimal(str(row["high"])),
                        low=Decimal(str(row["low"])),
                        close_raw=Decimal(str(row["close"])),
                        close_adj=None,
                        volume=int(row["volume"]),
                        vwap=None,
                        trade_count=None,
                        provider="tradier",
                    )
                )

        return sorted(bars, key=lambda b: b.timestamp)

    def normalize_quote(self, raw: Any) -> Quote:
        """Convert a tuple ``(data, ticker)`` to a Quote.

        *data* is the JSON dict from ``GET /v1/markets/quotes``.
        Expected shape: ``{"quotes": {"quote": {...}}}``.
        """
        try:
            data, ticker = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "TradierNormalizer.normalize_quote expects (data, ticker)",
                provider="tradier",
            ) from exc

        if not data:
            raise ValidationError(
                f"Tradier returned empty quote data for {ticker}",
                provider="tradier",
                ticker=ticker,
            )

        quotes = data.get("quotes") or {}
        q = quotes.get("quote") or {}
        if not q:
            raise ValidationError(
                f"Tradier returned no quote for {ticker}",
                provider="tradier",
                ticker=ticker,
            )

        last_val = _dec(q.get("last")) or Decimal("0")

        return Quote(
            ticker=ticker.upper(),
            timestamp=datetime.now(timezone.utc),
            bid=_dec(q.get("bid")),
            ask=_dec(q.get("ask")),
            bid_size=q.get("bidsize"),
            ask_size=q.get("asksize"),
            last=last_val,
            last_size=None,
            volume=q.get("volume"),
            open=_dec(q.get("open")),
            high=_dec(q.get("high")),
            low=_dec(q.get("low")),
            close=_dec(q.get("prevclose")),
            change=None,
            change_pct=None,
            provider="tradier",
        )

    def normalize_ticker_info(self, raw: Any) -> TickerInfo:
        """Not supported by Tradier."""
        raise NotImplementedError(
            "Tradier does not provide company info. Use yfinance for TickerInfo."
        )
