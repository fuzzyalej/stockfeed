"""Alpaca → options model normalizer."""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
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

# OCC symbol pattern: e.g. AAPL240119C00150000
_OCC_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def parse_occ_symbol(symbol: str) -> tuple[str, date, OptionType, Decimal]:
    """Parse an OCC option symbol into its components.

    Returns
    -------
    tuple[str, date, OptionType, Decimal]
        (underlying, expiration, option_type, strike)
    """
    m = _OCC_RE.match(symbol)
    if not m:
        raise ValueError(f"Cannot parse OCC symbol: {symbol!r}")
    underlying = m.group(1)
    exp_str = m.group(2)  # YYMMDD
    cp = m.group(3)
    strike_str = m.group(4)

    expiration = date(
        year=2000 + int(exp_str[:2]),
        month=int(exp_str[2:4]),
        day=int(exp_str[4:6]),
    )
    option_type = OptionType.CALL if cp == "C" else OptionType.PUT
    strike = Decimal(strike_str) / Decimal("1000")
    return underlying, expiration, option_type, strike


class AlpacaOptionsNormalizer:
    """Normalize Alpaca options API responses into canonical models.

    Uses greeks from the Alpaca API when available (``GreeksSource.API``);
    falls back to Black-Scholes calculation (``GreeksSource.CALCULATED``)
    when greeks are absent but implied volatility is present.

    Parameters
    ----------
    risk_free_rate : Decimal
        Annualised risk-free rate used for Black-Scholes fallback.
    """

    def __init__(self, risk_free_rate: Decimal) -> None:
        self._risk_free_rate = risk_free_rate
        self._calculator = GreeksCalculator()

    def normalize_expirations(self, raw: dict[str, Any]) -> list[date]:
        """Parse GET /v1beta1/options/contracts response body.

        Extracts unique, sorted expiration dates from the ``option_contracts``
        list in the response.
        """
        contracts = raw.get("option_contracts") or []
        dates: set[date] = set()
        for c in contracts:
            exp = c.get("expiration_date")
            if exp:
                dates.add(date.fromisoformat(exp))
        return sorted(dates)

    def normalize_chain(
        self, underlying: str, expiration: date, raw: dict[str, Any]
    ) -> OptionChain:
        """Parse the snapshots dict from GET /v1beta1/options/snapshots/{underlying}.

        Parameters
        ----------
        underlying:
            The underlying ticker symbol.
        expiration:
            The expiration date filter that was used in the request.
        raw:
            The ``snapshots`` dict from the API response (symbol → snapshot).
        """
        contracts: list[OptionContract] = []
        for symbol, snapshot in raw.items():
            contracts.append(self._snapshot_to_contract(symbol, underlying, expiration, snapshot))
        return OptionChain(
            underlying=underlying.upper(),
            expiration=expiration,
            contracts=contracts,
            provider="alpaca",
        )

    def normalize_option_quote(self, symbol: str, raw: dict[str, Any]) -> OptionQuote:
        """Parse a single snapshot entry into an OptionQuote.

        Parameters
        ----------
        symbol:
            The OCC option symbol.
        raw:
            The snapshot dict for the single contract.
        """
        details = raw.get("details") or {}
        underlying = str(details.get("underlyingSymbol", "")).upper()

        latest_quote = raw.get("latestQuote") or {}
        latest_trade = raw.get("latestTrade") or {}

        bid = self._dec(latest_quote.get("bp"))
        ask = self._dec(latest_quote.get("ap"))
        last = self._dec(latest_trade.get("p"))
        volume = self._safe_int(latest_trade.get("s"))
        open_interest = self._safe_int(details.get("openInterest"))
        iv = self._dec(raw.get("impliedVolatility"))
        underlying_price = self._dec(raw.get("underlyingPrice"))

        greeks = self._resolve_greeks(raw, symbol, iv, underlying_price=underlying_price)

        return OptionQuote(
            symbol=symbol,
            underlying=underlying,
            timestamp=datetime.now(timezone.utc),
            bid=bid,
            ask=ask,
            last=last,
            volume=volume,
            open_interest=open_interest,
            implied_volatility=iv,
            greeks=greeks,
            provider="alpaca",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _snapshot_to_contract(
        self,
        symbol: str,
        underlying: str,
        expiration: date,
        snapshot: dict[str, Any],
    ) -> OptionContract:
        details = snapshot.get("details") or {}
        latest_quote = snapshot.get("latestQuote") or {}
        latest_trade = snapshot.get("latestTrade") or {}

        raw_type = str(details.get("type", "")).lower()
        opt_type = OptionType.CALL if raw_type == "call" else OptionType.PUT

        bid = self._dec(latest_quote.get("bp"))
        ask = self._dec(latest_quote.get("ap"))
        last = self._dec(latest_trade.get("p"))
        volume = self._safe_int(latest_trade.get("s"))
        open_interest = self._safe_int(details.get("openInterest"))
        strike = self._dec(details.get("strikePrice")) or Decimal("0")
        iv = self._dec(snapshot.get("impliedVolatility"))
        underlying_price = self._dec(snapshot.get("underlyingPrice"))

        greeks = self._resolve_greeks(
            snapshot, symbol, iv, strike, opt_type, expiration, underlying_price
        )

        return OptionContract(
            symbol=symbol,
            underlying=underlying.upper(),
            expiration=expiration,
            strike=strike,
            option_type=opt_type,
            bid=bid,
            ask=ask,
            last=last,
            volume=volume,
            open_interest=open_interest,
            implied_volatility=iv,
            greeks=greeks,
            provider="alpaca",
        )

    def _resolve_greeks(
        self,
        snapshot: dict[str, Any],
        symbol: str,
        iv: Decimal | None,
        strike: Decimal | None = None,
        opt_type: OptionType | None = None,
        expiration: date | None = None,
        underlying_price: Decimal | None = None,
    ) -> Greeks | None:
        """Determine greeks from snapshot data.

        Priority:
        1. API greeks if present and non-null.
        2. Black-Scholes if IV and underlying price are available.
        3. None otherwise.
        """
        api_greeks = self._parse_api_greeks(snapshot.get("greeks"))
        if api_greeks is not None:
            return api_greeks

        if iv is None:
            return None

        # Attempt Black-Scholes calculation — requires underlying price
        if underlying_price is None or underlying_price <= 0:
            return None

        # Fill in strike/type/expiration from OCC symbol when not passed directly
        if strike is None or opt_type is None or expiration is None:
            try:
                _, expiration, opt_type, strike = parse_occ_symbol(symbol)
            except ValueError:
                return None

        if strike <= 0:
            return None

        return self._calculator.calculate(
            option_type=opt_type,
            underlying_price=underlying_price,
            strike=strike,
            expiration=expiration,
            risk_free_rate=self._risk_free_rate,
            implied_volatility=iv,
        )

    def _parse_api_greeks(self, greeks_data: Any) -> Greeks | None:
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
