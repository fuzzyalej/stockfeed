"""Black-Scholes greeks calculator — no external dependencies."""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

from stockfeed.models.options import Greeks, GreeksSource, OptionType


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via math.erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


class GreeksCalculator:
    """Compute option greeks via Black-Scholes.

    Usage
    -----
    calc = GreeksCalculator()
    greeks = calc.calculate(
        option_type=OptionType.CALL,
        underlying_price=Decimal("150"),
        strike=Decimal("155"),
        expiration=date(2026, 6, 20),
        risk_free_rate=Decimal("0.05"),
        implied_volatility=Decimal("0.25"),
    )
    # greeks.source == GreeksSource.CALCULATED always
    """

    def calculate(
        self,
        option_type: OptionType,
        underlying_price: Decimal,
        strike: Decimal,
        expiration: date,
        risk_free_rate: Decimal,
        implied_volatility: Decimal,
        today: date | None = None,
    ) -> Greeks:
        """Return Black-Scholes greeks.

        If *expiration* is in the past (T <= 0), all greek values are ``None``.
        ``source`` is always ``CALCULATED``.

        Parameters
        ----------
        option_type : OptionType
        underlying_price : Decimal
            Current price of the underlying (S).
        strike : Decimal
            Option strike price (K).
        expiration : date
            Expiration date of the option.
        risk_free_rate : Decimal
            Annualised risk-free rate (e.g. Decimal("0.05") for 5%).
        implied_volatility : Decimal
            Annualised implied volatility (e.g. Decimal("0.25") for 25%).
        today : date | None
            Reference date. Defaults to date.today().
        """
        if today is None:
            today = date.today()

        T = (expiration - today).days / 365.0

        if T <= 0:
            return Greeks(
                delta=None,
                gamma=None,
                theta=None,
                vega=None,
                rho=None,
                source=GreeksSource.CALCULATED,
            )

        S = float(underlying_price)
        K = float(strike)
        r = float(risk_free_rate)
        sigma = float(implied_volatility)

        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        pdf_d1 = _norm_pdf(d1)
        cdf_d1 = _norm_cdf(d1)
        cdf_d2 = _norm_cdf(d2)
        cdf_neg_d2 = _norm_cdf(-d2)
        exp_neg_rT = math.exp(-r * T)

        if option_type == OptionType.CALL:
            delta = cdf_d1
            theta = (-(S * pdf_d1 * sigma / (2 * sqrt_T)) - r * K * exp_neg_rT * cdf_d2) / 365.0
            rho = K * T * exp_neg_rT * cdf_d2
        else:
            delta = cdf_d1 - 1.0
            theta = (-(S * pdf_d1 * sigma / (2 * sqrt_T)) + r * K * exp_neg_rT * cdf_neg_d2) / 365.0
            rho = -K * T * exp_neg_rT * cdf_neg_d2

        gamma = pdf_d1 / (S * sigma * sqrt_T)
        vega = S * pdf_d1 * sqrt_T / 100.0  # per 1% change in IV

        def _d(v: float) -> Decimal:
            return Decimal(str(round(v, 6)))

        return Greeks(
            delta=_d(delta),
            gamma=_d(gamma),
            theta=_d(theta),
            vega=_d(vega),
            rho=_d(rho),
            source=GreeksSource.CALCULATED,
        )
