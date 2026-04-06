"""Tradier → options model normalizer."""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from typing import Any

from stockfeed.models.options import (
    Greeks,
    GreeksSource,
    OptionChain,
    OptionContract,
    OptionQuote,
    OptionType,
)
from stockfeed.options.greeks import GreeksCalculator


class TradierOptionsNormalizer:
    """Normalize Tradier options API responses into canonical models.

    Uses greeks from the Tradier API when available (``GreeksSource.API``);
    falls back to Black-Scholes calculation (``GreeksSource.CALCULATED``)
    when the API does not return them.

    Parameters
    ----------
    risk_free_rate : Decimal
        Annualised risk-free rate used for Black-Scholes fallback.
    """

    def __init__(self, risk_free_rate: Decimal) -> None:
        self._risk_free_rate = risk_free_rate
        self._calculator = GreeksCalculator()

    def normalize_expirations(self, data: dict[str, Any]) -> list[date]:
        """Parse GET /v1/markets/options/expirations response."""
        dates = data.get("expirations", {}).get("date", [])
        if isinstance(dates, str):
            dates = [dates]
        return [date.fromisoformat(d) for d in dates]

    def normalize_chain(
        self, underlying: str, expiration: date, data: dict[str, Any]
    ) -> OptionChain:
        """Parse GET /v1/markets/options/chains response."""
        options = data.get("options", {}).get("option", [])
        if isinstance(options, dict):
            options = [options]
        contracts = [self._to_contract(o, underlying, expiration) for o in (options or [])]
        return OptionChain(
            underlying=underlying.upper(),
            expiration=expiration,
            contracts=contracts,
            provider="tradier",
        )

    def normalize_option_quote(self, symbol: str, data: dict[str, Any]) -> OptionQuote:
        """Parse GET /v1/markets/options/quotes response for a single contract."""
        from datetime import datetime, timezone

        opt = data.get("quotes", {}).get("quote", {})
        greeks = self._parse_greeks(opt.get("greeks"))
        return OptionQuote(
            symbol=symbol,
            underlying=str(opt.get("root_symbol", "")).upper(),
            bid=self._dec(opt.get("bid")),
            ask=self._dec(opt.get("ask")),
            last=self._dec(opt.get("last")),
            volume=opt.get("volume"),
            open_interest=opt.get("open_interest"),
            implied_volatility=self._dec(opt.get("implied_volatility")),
            greeks=greeks,
            timestamp=datetime.now(timezone.utc),
            provider="tradier",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _to_contract(
        self, opt: dict[str, Any], underlying: str, expiration: date
    ) -> OptionContract:
        iv = self._dec(opt.get("implied_volatility"))
        api_greeks = self._parse_greeks(opt.get("greeks"))

        if api_greeks is None and iv is not None:
            underlying_price = self._dec(opt.get("underlying_price") or opt.get("root_price"))
            if underlying_price and underlying_price > 0:
                strike = self._dec(opt.get("strike"))
                if strike and strike > 0:
                    raw_type = str(opt.get("option_type", "")).lower()
                    opt_type = OptionType.CALL if raw_type == "call" else OptionType.PUT
                    api_greeks = self._calculator.calculate(
                        option_type=opt_type,
                        underlying_price=underlying_price,
                        strike=strike,
                        expiration=expiration,
                        risk_free_rate=self._risk_free_rate,
                        implied_volatility=iv,
                    )

        raw_type = str(opt.get("option_type", "")).lower()
        opt_type = OptionType.CALL if raw_type == "call" else OptionType.PUT

        return OptionContract(
            symbol=str(opt.get("symbol", "")),
            underlying=underlying.upper(),
            expiration=expiration,
            strike=self._dec(opt.get("strike")) or Decimal("0"),
            option_type=opt_type,
            bid=self._dec(opt.get("bid")),
            ask=self._dec(opt.get("ask")),
            last=self._dec(opt.get("last")),
            volume=opt.get("volume"),
            open_interest=opt.get("open_interest"),
            implied_volatility=iv,
            greeks=api_greeks,
            provider="tradier",
        )

    def _parse_greeks(self, greeks_data: Any) -> Greeks | None:
        if not greeks_data:
            return None
        d = self._dec(greeks_data.get("delta"))
        g = self._dec(greeks_data.get("gamma"))
        t = self._dec(greeks_data.get("theta"))
        v = self._dec(greeks_data.get("vega"))
        r = self._dec(greeks_data.get("rho"))
        if all(x is None for x in [d, g, t, v, r]):
            return None
        return Greeks(delta=d, gamma=g, theta=t, vega=v, rho=r, source=GreeksSource.API)

    @staticmethod
    def _dec(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            f = float(value)
            if math.isnan(f) or math.isinf(f):
                return None
            return Decimal(str(f))
        except (TypeError, ValueError):
            return None
