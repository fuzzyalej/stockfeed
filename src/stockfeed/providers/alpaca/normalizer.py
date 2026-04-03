"""Alpaca → canonical model normalizer."""

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
    """Parse an ISO-8601 timestamp from Alpaca into a UTC datetime."""
    s = val.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class AlpacaNormalizer(BaseNormalizer):
    """Normalize Alpaca Markets REST responses into canonical models."""

    def normalize_ohlcv(self, raw: Any) -> list[OHLCVBar]:
        """Convert a tuple ``(bars_list, ticker, interval)`` to a list of OHLCVBar.

        *bars_list* is the accumulated list of bar dicts from all pages of
        ``GET /v2/stocks/{ticker}/bars``.
        Each bar has keys: ``t``, ``o``, ``h``, ``l``, ``c``, ``v``, ``vw``, ``n``.
        """
        try:
            bars_list, ticker, interval = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "AlpacaNormalizer.normalize_ohlcv expects (bars_list, ticker, interval)",
                provider="alpaca",
            ) from exc

        if not bars_list:
            raise ValidationError(
                f"Alpaca returned no OHLCV data for {ticker}",
                provider="alpaca",
                ticker=ticker,
                suggestion="Check that the ticker exists and the date range is valid.",
            )

        bars: list[OHLCVBar] = []
        for row in bars_list:
            dt = _parse_dt(str(row["t"]))
            vwap = _dec(row.get("vw"))
            trade_count = row.get("n")
            bars.append(
                OHLCVBar(
                    ticker=ticker.upper(),
                    timestamp=dt,
                    interval=interval,
                    open=Decimal(str(row["o"])),
                    high=Decimal(str(row["h"])),
                    low=Decimal(str(row["l"])),
                    close_raw=Decimal(str(row["c"])),
                    close_adj=None,
                    volume=int(row.get("v") or 0),
                    vwap=vwap,
                    trade_count=int(trade_count) if trade_count is not None else None,
                    provider="alpaca",
                )
            )

        return sorted(bars, key=lambda b: b.timestamp)

    def normalize_quote(self, raw: Any) -> Quote:
        """Convert a tuple ``(quote_data, trade_data, ticker)`` to a Quote.

        *quote_data* is from ``GET /v2/stocks/{ticker}/quotes/latest`` and
        *trade_data* is from ``GET /v2/stocks/{ticker}/trades/latest``.
        """
        try:
            quote_data, trade_data, ticker = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "AlpacaNormalizer.normalize_quote expects (quote_data, trade_data, ticker)",
                provider="alpaca",
            ) from exc

        if not quote_data and not trade_data:
            raise ValidationError(
                f"Alpaca returned empty quote/trade data for {ticker}",
                provider="alpaca",
                ticker=ticker,
            )

        q = quote_data.get("quote", {}) if quote_data else {}
        t = trade_data.get("trade", {}) if trade_data else {}

        last_val = _dec(t.get("p")) or Decimal("0")
        last_size = t.get("s")

        return Quote(
            ticker=ticker.upper(),
            timestamp=datetime.now(timezone.utc),
            bid=_dec(q.get("bp")),
            ask=_dec(q.get("ap")),
            bid_size=int(q["bs"]) if q.get("bs") is not None else None,
            ask_size=int(q["as"]) if q.get("as") is not None else None,
            last=last_val,
            last_size=int(last_size) if last_size is not None else None,
            volume=None,
            open=None,
            high=None,
            low=None,
            close=None,
            change=None,
            change_pct=None,
            provider="alpaca",
        )

    def normalize_ticker_info(self, raw: Any) -> TickerInfo:
        """Convert a tuple ``(data, ticker)`` to a TickerInfo.

        *data* is the JSON dict from ``GET /v2/assets/{ticker}``.
        Keys: ``id``, ``class``, ``exchange``, ``symbol``, ``name``, ``status``.
        """
        try:
            data, ticker = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "AlpacaNormalizer.normalize_ticker_info expects (data, ticker)",
                provider="alpaca",
            ) from exc

        if not data:
            raise ValidationError(
                f"Alpaca returned empty asset data for {ticker}",
                provider="alpaca",
                ticker=ticker,
            )

        return TickerInfo(
            ticker=ticker.upper(),
            name=data.get("name") or ticker,
            exchange=data.get("exchange") or "UNKNOWN",
            currency="USD",  # Alpaca only supports US equities (USD)
            country="US",
            sector=None,
            industry=None,
            market_cap=None,
            provider="alpaca",
        )
