"""yfinance → canonical model normalizer."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd

from stockfeed.exceptions import ValidationError
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo
from stockfeed.normalizer.base import BaseNormalizer

# Map yfinance period/interval strings to Interval enum
_YF_INTERVAL_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1wk": "1w",
    "1mo": "1mo",
}


class YFinanceNormalizer(BaseNormalizer):
    """Normalize yfinance DataFrames and info dicts into canonical models."""

    def normalize_ohlcv(self, raw: Any) -> list[OHLCVBar]:
        """Convert a tuple of (raw_df, adj_df, ticker, interval) to OHLCVBar list.

        Parameters
        ----------
        raw : tuple
            ``(raw_df, adj_df, ticker, interval)`` where *raw_df* is the
            unadjusted history DataFrame and *adj_df* is the adjusted one.

        Raises
        ------
        ValidationError
            If the DataFrames are empty or missing expected columns.
        """
        try:
            raw_df, adj_df, ticker, interval = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "YFinanceNormalizer.normalize_ohlcv expects (raw_df, adj_df, ticker, interval)",
                provider="yfinance",
                ticker=str(raw) if not isinstance(raw, tuple) else None,
            ) from exc

        if not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
            raise ValidationError(
                f"yfinance returned no data for {ticker}",
                provider="yfinance",
                ticker=ticker,
                suggestion="Check that the ticker exists and the date range is valid.",
            )

        required_cols = {"Open", "High", "Low", "Close", "Volume"}
        missing = required_cols - set(raw_df.columns)
        if missing:
            raise ValidationError(
                f"yfinance OHLCV response missing columns: {missing}",
                provider="yfinance",
                ticker=ticker,
            )

        bars: list[OHLCVBar] = []
        for ts, row in raw_df.iterrows():
            # Timestamps from yfinance are timezone-aware; normalise to UTC
            if isinstance(ts, pd.Timestamp):
                dt = ts.to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
            else:
                dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)

            # Adjusted close from the adj_df (may be absent)
            close_adj: Decimal | None = None
            if isinstance(adj_df, pd.DataFrame) and not adj_df.empty and ts in adj_df.index:
                adj_val = adj_df.loc[ts, "Close"]
                if pd.notna(adj_val):
                    close_adj = Decimal(str(adj_val))

            bars.append(
                OHLCVBar(
                    ticker=ticker.upper(),
                    timestamp=dt,
                    interval=interval,
                    open=Decimal(str(row["Open"])),
                    high=Decimal(str(row["High"])),
                    low=Decimal(str(row["Low"])),
                    close_raw=Decimal(str(row["Close"])),
                    close_adj=close_adj,
                    volume=int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
                    vwap=None,
                    trade_count=None,
                    provider="yfinance",
                )
            )

        return sorted(bars, key=lambda b: b.timestamp)

    def normalize_quote(self, raw: Any) -> Quote:
        """Convert yfinance fast_info / info dict to a Quote.

        Parameters
        ----------
        raw : tuple
            ``(info, ticker)`` where *info* is the dict from
            ``yf.Ticker.fast_info`` or ``.info``.
        """
        try:
            info, ticker = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "YFinanceNormalizer.normalize_quote expects (info_dict, ticker)",
                provider="yfinance",
            ) from exc

        if not info:
            raise ValidationError(
                f"yfinance returned empty info for {ticker}",
                provider="yfinance",
                ticker=ticker,
                suggestion="The ticker may be delisted or not available on yfinance.",
            )

        def _dec(key: str) -> Decimal | None:
            val = info.get(key)
            if val is None or (isinstance(val, float) and val != val):  # NaN check
                return None
            return Decimal(str(val))

        last = _dec("currentPrice") or _dec("regularMarketPrice") or _dec("ask") or Decimal("0")

        return Quote(
            ticker=ticker.upper(),
            timestamp=datetime.now(timezone.utc),
            bid=_dec("bid"),
            ask=_dec("ask"),
            bid_size=info.get("bidSize"),
            ask_size=info.get("askSize"),
            last=last,
            last_size=None,
            volume=info.get("volume") or info.get("regularMarketVolume"),
            open=_dec("open") or _dec("regularMarketOpen"),
            high=_dec("dayHigh") or _dec("regularMarketDayHigh"),
            low=_dec("dayLow") or _dec("regularMarketDayLow"),
            close=_dec("previousClose") or _dec("regularMarketPreviousClose"),
            change=None,
            change_pct=None,
            provider="yfinance",
        )

    def normalize_ticker_info(self, raw: Any) -> TickerInfo:
        """Convert a yfinance info dict to TickerInfo.

        Parameters
        ----------
        raw : tuple
            ``(info_dict, ticker)``.
        """
        try:
            info, ticker = raw
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "YFinanceNormalizer.normalize_ticker_info expects (info_dict, ticker)",
                provider="yfinance",
            ) from exc

        if not info:
            raise ValidationError(
                f"yfinance returned empty info for {ticker}",
                provider="yfinance",
                ticker=ticker,
                suggestion="The ticker may be delisted or not available on yfinance.",
            )

        return TickerInfo(
            ticker=ticker.upper(),
            name=info.get("longName") or info.get("shortName") or ticker,
            exchange=info.get("exchange") or info.get("fullExchangeName") or "UNKNOWN",
            currency=info.get("currency") or "USD",
            country=info.get("country"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            market_cap=info.get("marketCap"),
            provider="yfinance",
        )
