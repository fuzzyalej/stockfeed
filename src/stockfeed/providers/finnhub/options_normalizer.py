"""Finnhub → options model normalizer."""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from typing import Any

from stockfeed.exceptions import TickerNotFoundError
from stockfeed.models.options import (
    OptionChain,
    OptionContract,
    OptionType,
)
from stockfeed.options.greeks import GreeksCalculator


class FinnhubOptionsNormalizer:
    """Normalize Finnhub option-chain API responses into canonical models.

    Finnhub does not provide greeks — they are always computed via
    :class:`~stockfeed.options.greeks.GreeksCalculator` when IV and an
    underlying price are available.

    Parameters
    ----------
    risk_free_rate : Decimal
        Annualised risk-free rate used for Black-Scholes greeks.
    """

    def __init__(self, risk_free_rate: Decimal) -> None:
        self._risk_free_rate = risk_free_rate
        self._calculator = GreeksCalculator()

    def normalize_chain(
        self,
        underlying: str,
        expiration: date,
        raw: dict,
        underlying_price: Decimal | None = None,
    ) -> OptionChain:
        """Convert a Finnhub option-chain response to an OptionChain.

        Parameters
        ----------
        underlying : str
            Ticker symbol.
        expiration : date
            The expiration date to filter for.
        raw : dict
            Full API response body (contains ``data`` list).
        underlying_price : Decimal | None
            Current underlying price used for BS greeks calculation.
            If ``None``, greeks will not be calculated.
        """
        exp_str = expiration.isoformat()
        data_blocks: list[dict] = raw.get("data") or []

        matching = [block for block in data_blocks if block.get("expirationDate") == exp_str]
        if not matching:
            raise TickerNotFoundError(
                f"Finnhub returned no option data for {underlying} expiring {exp_str}",
                provider="finnhub",
                ticker=underlying,
            )

        contracts: list[OptionContract] = []
        for block in matching:
            options: dict = block.get("options") or {}
            calls: list[dict] = options.get("CALL") or []
            puts: list[dict] = options.get("PUT") or []

            for raw_contract in calls:
                contracts.append(
                    self._raw_to_contract(
                        raw_contract, underlying, expiration, OptionType.CALL, underlying_price
                    )
                )
            for raw_contract in puts:
                contracts.append(
                    self._raw_to_contract(
                        raw_contract, underlying, expiration, OptionType.PUT, underlying_price
                    )
                )

        return OptionChain(
            underlying=underlying.upper(),
            expiration=expiration,
            contracts=contracts,
            provider="finnhub",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _raw_to_contract(
        self,
        raw: dict,
        underlying: str,
        expiration: date,
        option_type: OptionType,
        underlying_price: Decimal | None,
    ) -> OptionContract:
        iv = self._safe_decimal(raw.get("impliedVolatility"))
        strike = self._safe_decimal(raw.get("strike"))

        greeks = None
        if (
            iv is not None
            and underlying_price is not None
            and underlying_price > 0
            and strike is not None
            and strike > 0
        ):
            greeks = self._calculator.calculate(
                option_type=option_type,
                underlying_price=underlying_price,
                strike=strike,
                expiration=expiration,
                risk_free_rate=self._risk_free_rate,
                implied_volatility=iv,
            )

        return OptionContract(
            symbol=str(raw.get("contractName", "")),
            underlying=underlying.upper(),
            expiration=expiration,
            strike=strike or Decimal("0"),
            option_type=option_type,
            bid=self._safe_decimal(raw.get("bid")),
            ask=self._safe_decimal(raw.get("ask")),
            last=self._safe_decimal(raw.get("lastPrice")),
            volume=self._safe_int(raw.get("volume")),
            open_interest=self._safe_int(raw.get("openInterest")),
            implied_volatility=iv,
            greeks=greeks,
            provider="finnhub",
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
            if math.isnan(f) or math.isinf(f):
                return None
            return int(f)
        except (TypeError, ValueError):
            return None
