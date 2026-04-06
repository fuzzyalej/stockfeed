"""yfinance → options model normalizer."""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from stockfeed.models.options import (
    OptionChain,
    OptionContract,
    OptionQuote,
    OptionType,
)
from stockfeed.options.greeks import GreeksCalculator


class YFinanceOptionsNormalizer:
    """Normalize yfinance options DataFrames into canonical models.

    yfinance does not provide greeks — they are always computed via
    :class:`~stockfeed.options.greeks.GreeksCalculator`.

    Parameters
    ----------
    risk_free_rate : Decimal
        Annualised risk-free rate used for Black-Scholes greeks.
    """

    def __init__(self, risk_free_rate: Decimal) -> None:
        self._risk_free_rate = risk_free_rate
        self._calculator = GreeksCalculator()

    def normalize_expirations(self, raw: tuple[str, ...]) -> list[date]:
        """Convert yfinance expiration strings to dates.

        Parameters
        ----------
        raw : tuple[str, ...]
            ``yf.Ticker.options`` — a tuple of "YYYY-MM-DD" strings.
        """
        return [date.fromisoformat(s) for s in raw]

    def normalize_chain(
        self,
        underlying: str,
        expiration: date,
        calls_df: pd.DataFrame,
        puts_df: pd.DataFrame,
        underlying_price: Decimal,
    ) -> OptionChain:
        """Convert calls/puts DataFrames to an OptionChain."""
        contracts: list[OptionContract] = []
        for df, opt_type in [(calls_df, OptionType.CALL), (puts_df, OptionType.PUT)]:
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                contracts.append(
                    self._row_to_contract(row, underlying, expiration, opt_type, underlying_price)
                )
        return OptionChain(
            underlying=underlying.upper(),
            expiration=expiration,
            contracts=contracts,
            provider="yfinance",
        )

    def normalize_option_quote(self, symbol: str, row: Any, underlying: str) -> OptionQuote:
        """Convert a single yfinance options row to an OptionQuote."""
        from datetime import datetime, timezone

        iv = self._safe_decimal(row.get("impliedVolatility"))
        return OptionQuote(
            symbol=symbol,
            underlying=underlying.upper(),
            bid=self._safe_decimal(row.get("bid")),
            ask=self._safe_decimal(row.get("ask")),
            last=self._safe_decimal(row.get("lastPrice")),
            volume=self._safe_int(row.get("volume")),
            open_interest=self._safe_int(row.get("openInterest")),
            implied_volatility=iv,
            greeks=None,  # no underlying price available here; greeks skipped
            timestamp=datetime.now(timezone.utc),
            provider="yfinance",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _row_to_contract(
        self,
        row: Any,
        underlying: str,
        expiration: date,
        option_type: OptionType,
        underlying_price: Decimal,
    ) -> OptionContract:
        iv = self._safe_decimal(row.get("impliedVolatility"))
        greeks = None
        if iv is not None and underlying_price > 0:
            strike = self._safe_decimal(row.get("strike"))
            if strike and strike > 0:
                greeks = self._calculator.calculate(
                    option_type=option_type,
                    underlying_price=underlying_price,
                    strike=strike,
                    expiration=expiration,
                    risk_free_rate=self._risk_free_rate,
                    implied_volatility=iv,
                )
        return OptionContract(
            symbol=str(row.get("contractSymbol", "")),
            underlying=underlying.upper(),
            expiration=expiration,
            strike=self._safe_decimal(row.get("strike")) or Decimal("0"),
            option_type=option_type,
            bid=self._safe_decimal(row.get("bid")),
            ask=self._safe_decimal(row.get("ask")),
            last=self._safe_decimal(row.get("lastPrice")),
            volume=self._safe_int(row.get("volume")),
            open_interest=self._safe_int(row.get("openInterest")),
            implied_volatility=iv,
            greeks=greeks,
            provider="yfinance",
        )

    @staticmethod
    def _safe_decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            f = float(value)
            if math.isnan(f) or math.isinf(f):
                return None
            return Decimal(str(f))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            f = float(value)
            if math.isnan(f):
                return None
            return int(f)
        except (TypeError, ValueError):
            return None
