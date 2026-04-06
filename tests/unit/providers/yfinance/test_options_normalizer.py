from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from stockfeed.models.options import GreeksSource, OptionType
from stockfeed.providers.yfinance.options_normalizer import YFinanceOptionsNormalizer


@pytest.fixture
def normalizer():
    return YFinanceOptionsNormalizer(risk_free_rate=Decimal("0.05"))


@pytest.fixture
def sample_calls_df():
    return pd.DataFrame(
        [
            {
                "contractSymbol": "AAPL260701C00150000",
                "strike": 150.0,
                "lastPrice": 1.52,
                "bid": 1.50,
                "ask": 1.55,
                "volume": 100.0,
                "openInterest": 500.0,
                "impliedVolatility": 0.25,
            }
        ]
    )


@pytest.fixture
def sample_puts_df():
    return pd.DataFrame(
        [
            {
                "contractSymbol": "AAPL260701P00150000",
                "strike": 150.0,
                "lastPrice": 2.10,
                "bid": 2.05,
                "ask": 2.15,
                "volume": 80.0,
                "openInterest": 300.0,
                "impliedVolatility": 0.28,
            }
        ]
    )


def test_normalize_expirations(normalizer):
    raw = ("2024-01-19", "2024-03-15")
    result = normalizer.normalize_expirations(raw)
    assert result == [date(2024, 1, 19), date(2024, 3, 15)]
    assert all(isinstance(d, date) for d in result)


def test_normalize_chain_contains_calls_and_puts(normalizer, sample_calls_df, sample_puts_df):
    chain = normalizer.normalize_chain(
        underlying="AAPL",
        expiration=date(2026, 7, 1),
        calls_df=sample_calls_df,
        puts_df=sample_puts_df,
        underlying_price=Decimal("155"),
    )
    assert chain.underlying == "AAPL"
    assert chain.expiration == date(2026, 7, 1)
    assert chain.provider == "yfinance"
    calls = [c for c in chain.contracts if c.option_type == OptionType.CALL]
    puts = [c for c in chain.contracts if c.option_type == OptionType.PUT]
    assert len(calls) == 1
    assert len(puts) == 1


def test_normalize_chain_greeks_always_calculated(normalizer, sample_calls_df, sample_puts_df):
    """yfinance never provides greeks — source must always be CALCULATED."""
    chain = normalizer.normalize_chain(
        underlying="AAPL",
        expiration=date(2026, 7, 1),
        calls_df=sample_calls_df,
        puts_df=sample_puts_df,
        underlying_price=Decimal("155"),
    )
    for contract in chain.contracts:
        if contract.greeks is not None:
            assert contract.greeks.source == GreeksSource.CALCULATED


def test_normalize_chain_missing_iv_gives_no_greeks(normalizer):
    """Contracts with NaN IV should have greeks=None."""
    df = pd.DataFrame(
        [
            {
                "contractSymbol": "AAPL260701C00150000",
                "strike": 150.0,
                "lastPrice": 1.52,
                "bid": None,
                "ask": None,
                "volume": None,
                "openInterest": None,
                "impliedVolatility": float("nan"),
            }
        ]
    )
    chain = normalizer.normalize_chain(
        underlying="AAPL",
        expiration=date(2026, 7, 1),
        calls_df=df,
        puts_df=pd.DataFrame(),
        underlying_price=Decimal("155"),
    )
    assert chain.contracts[0].greeks is None


def test_normalize_chain_underlying_uppercase(normalizer, sample_calls_df):
    chain = normalizer.normalize_chain(
        underlying="aapl",
        expiration=date(2026, 7, 1),
        calls_df=sample_calls_df,
        puts_df=pd.DataFrame(),
        underlying_price=Decimal("155"),
    )
    assert chain.underlying == "AAPL"
    assert all(c.underlying == "AAPL" for c in chain.contracts)
