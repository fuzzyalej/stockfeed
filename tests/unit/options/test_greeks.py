# tests/unit/options/test_greeks.py
from datetime import date
from decimal import Decimal

import pytest

from stockfeed.models.options import GreeksSource, OptionType
from stockfeed.options.greeks import GreeksCalculator


@pytest.fixture
def calc():
    return GreeksCalculator()


def test_call_delta_atm(calc):
    """ATM call delta should be close to 0.5."""
    g = calc.calculate(
        option_type=OptionType.CALL,
        underlying_price=Decimal("100"),
        strike=Decimal("100"),
        expiration=date(2026, 7, 1),
        risk_free_rate=Decimal("0.05"),
        implied_volatility=Decimal("0.20"),
        today=date(2026, 4, 6),
    )
    assert g.source == GreeksSource.CALCULATED
    assert g.delta is not None
    assert Decimal("0.45") < g.delta < Decimal("0.65")


def test_put_delta_atm(calc):
    """ATM put delta should be close to -0.5."""
    g = calc.calculate(
        option_type=OptionType.PUT,
        underlying_price=Decimal("100"),
        strike=Decimal("100"),
        expiration=date(2026, 7, 1),
        risk_free_rate=Decimal("0.05"),
        implied_volatility=Decimal("0.20"),
        today=date(2026, 4, 6),
    )
    assert g.delta is not None
    assert Decimal("-0.65") < g.delta < Decimal("-0.35")


def test_gamma_positive(calc):
    """Gamma is always positive."""
    g = calc.calculate(
        option_type=OptionType.CALL,
        underlying_price=Decimal("100"),
        strike=Decimal("100"),
        expiration=date(2026, 7, 1),
        risk_free_rate=Decimal("0.05"),
        implied_volatility=Decimal("0.20"),
        today=date(2026, 4, 6),
    )
    assert g.gamma is not None
    assert g.gamma > 0


def test_theta_negative_call(calc):
    """Theta is typically negative (time decay)."""
    g = calc.calculate(
        option_type=OptionType.CALL,
        underlying_price=Decimal("100"),
        strike=Decimal("100"),
        expiration=date(2026, 7, 1),
        risk_free_rate=Decimal("0.05"),
        implied_volatility=Decimal("0.20"),
        today=date(2026, 4, 6),
    )
    assert g.theta is not None
    assert g.theta < 0


def test_vega_positive(calc):
    """Vega is always positive."""
    g = calc.calculate(
        option_type=OptionType.CALL,
        underlying_price=Decimal("100"),
        strike=Decimal("100"),
        expiration=date(2026, 7, 1),
        risk_free_rate=Decimal("0.05"),
        implied_volatility=Decimal("0.20"),
        today=date(2026, 4, 6),
    )
    assert g.vega is not None
    assert g.vega > 0


def test_returns_none_greeks_when_expired(calc):
    """Expired options (T <= 0) should return all-None greeks."""
    g = calc.calculate(
        option_type=OptionType.CALL,
        underlying_price=Decimal("100"),
        strike=Decimal("100"),
        expiration=date(2025, 1, 1),
        risk_free_rate=Decimal("0.05"),
        implied_volatility=Decimal("0.20"),
        today=date(2026, 4, 6),
    )
    assert g.delta is None
    assert g.source == GreeksSource.CALCULATED


def test_put_call_parity_delta(calc):
    """Call delta + abs(put delta) should be approximately 1 for same strike."""
    call = calc.calculate(
        option_type=OptionType.CALL,
        underlying_price=Decimal("100"),
        strike=Decimal("100"),
        expiration=date(2026, 7, 1),
        risk_free_rate=Decimal("0.05"),
        implied_volatility=Decimal("0.20"),
        today=date(2026, 4, 6),
    )
    put = calc.calculate(
        option_type=OptionType.PUT,
        underlying_price=Decimal("100"),
        strike=Decimal("100"),
        expiration=date(2026, 7, 1),
        risk_free_rate=Decimal("0.05"),
        implied_volatility=Decimal("0.20"),
        today=date(2026, 4, 6),
    )
    assert abs(call.delta + abs(put.delta) - Decimal("1")) < Decimal("0.01")
