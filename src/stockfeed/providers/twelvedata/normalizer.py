"""Twelve Data → canonical model normalizer."""

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
    """Parse a Twelve Data datetime string into a UTC-aware datetime.

    Twelve Data returns strings like ``"2024-01-02 09:30:00"`` or
    ``"2024-01-02"``.
    """
    val = val.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(val, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Try ISO format as last resort
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError(f"Cannot parse Twelve Data datetime: {val!r}") from exc


class TwelvedataNormalizer(BaseNormalizer):
    """Normalize Twelve Data REST responses into canonical models."""

    def normalize_ohlcv(self, raw: Any) -> list[OHLCVBar]:
        """Convert a tuple ``(data, ticker, interval)`` to a list of OHLCVBar.

        *data* is the parsed JSON dict with a ``"values"`` key from the
        ``/time_series`` endpoint.
        """
        try:
            data, ticker, interval = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "TwelvedataNormalizer.normalize_ohlcv expects (data, ticker, interval)",
                provider="twelvedata",
            ) from exc

        if not data:
            raise ValidationError(
                f"Twelve Data returned no OHLCV data for {ticker}",
                provider="twelvedata",
                ticker=ticker,
            )

        values = data.get("values")
        if not values:
            raise ValidationError(
                f"Twelve Data returned empty values for {ticker}",
                provider="twelvedata",
                ticker=ticker,
                suggestion="Check that the ticker and date range are valid.",
            )

        bars: list[OHLCVBar] = []
        for row in values:
            dt = _parse_dt(str(row["datetime"]))
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
                    provider="twelvedata",
                )
            )

        return sorted(bars, key=lambda b: b.timestamp)

    def normalize_quote(self, raw: Any) -> Quote:
        """Convert a tuple ``(price_data, quote_data, ticker)`` to a Quote.

        *price_data* is from ``GET /price`` and *quote_data* is from
        ``GET /quote``.
        """
        try:
            price_data, quote_data, ticker = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "TwelvedataNormalizer.normalize_quote expects (price_data, quote_data, ticker)",
                provider="twelvedata",
            ) from exc

        if not price_data and not quote_data:
            raise ValidationError(
                f"Twelve Data returned empty price/quote data for {ticker}",
                provider="twelvedata",
                ticker=ticker,
            )

        # Price endpoint returns {"price": "188.32"}
        last_val = _dec(price_data.get("price") if price_data else None)
        if last_val is None and quote_data:
            last_val = _dec(quote_data.get("close"))
        if last_val is None:
            last_val = Decimal("0")

        q = quote_data or {}
        return Quote(
            ticker=ticker.upper(),
            timestamp=datetime.now(timezone.utc),
            bid=None,
            ask=None,
            bid_size=None,
            ask_size=None,
            last=last_val,
            last_size=None,
            volume=int(q["volume"]) if q.get("volume") is not None else None,
            open=_dec(q.get("open")),
            high=_dec(q.get("high")),
            low=_dec(q.get("low")),
            close=_dec(q.get("previous_close")),
            change=None,
            change_pct=None,
            provider="twelvedata",
        )

    def normalize_ticker_info(self, raw: Any) -> TickerInfo:
        """Convert a tuple ``(data, ticker)`` to a TickerInfo.

        *data* is the JSON dict from ``GET /profile``.
        Keys: ``name``, ``exchange``, ``currency``, ``country``, ``sector``,
        ``industry``.
        """
        try:
            data, ticker = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "TwelvedataNormalizer.normalize_ticker_info expects (data, ticker)",
                provider="twelvedata",
            ) from exc

        if not data:
            raise ValidationError(
                f"Twelve Data returned empty profile for {ticker}",
                provider="twelvedata",
                ticker=ticker,
            )

        return TickerInfo(
            ticker=ticker.upper(),
            name=data.get("name") or ticker,
            exchange=data.get("exchange") or "UNKNOWN",
            currency=data.get("currency") or "USD",
            country=data.get("country"),
            sector=data.get("sector"),
            industry=data.get("industry"),
            market_cap=None,
            provider="twelvedata",
        )
