from datetime import date
from decimal import Decimal

import pytest

from stockfeed.models.options import GreeksSource, OptionType
from stockfeed.providers.tradier.options_normalizer import TradierOptionsNormalizer


@pytest.fixture
def normalizer():
    return TradierOptionsNormalizer(risk_free_rate=Decimal("0.05"))


_CHAIN_WITH_GREEKS = {
    "options": {
        "option": [
            {
                "symbol": "AAPL240119C00150000",
                "underlying": "AAPL",
                "expiration_date": "2024-01-19",
                "strike": 150.0,
                "option_type": "call",
                "bid": 1.50,
                "ask": 1.55,
                "last": 1.52,
                "volume": 100,
                "open_interest": 500,
                "implied_volatility": 0.25,
                "greeks": {
                    "delta": 0.55,
                    "gamma": 0.02,
                    "theta": -0.05,
                    "vega": 0.10,
                    "rho": 0.01,
                },
            }
        ]
    }
}

_EXPIRATIONS_RESPONSE = {"expirations": {"date": ["2024-01-19", "2024-03-15"]}}


def test_normalize_expirations(normalizer):
    result = normalizer.normalize_expirations(_EXPIRATIONS_RESPONSE)
    assert result == [date(2024, 1, 19), date(2024, 3, 15)]


def test_normalize_chain_uses_api_greeks(normalizer):
    chain = normalizer.normalize_chain("AAPL", date(2024, 1, 19), _CHAIN_WITH_GREEKS)
    assert len(chain.contracts) == 1
    c = chain.contracts[0]
    assert c.option_type == OptionType.CALL
    assert c.greeks is not None
    assert c.greeks.source == GreeksSource.API
    assert c.greeks.delta == Decimal("0.55")
    assert c.greeks.gamma == Decimal("0.02")


def test_normalize_chain_bs_fallback_when_no_api_greeks(normalizer):
    response = {
        "options": {
            "option": [
                {
                    "symbol": "AAPL260701C00150000",
                    "underlying": "AAPL",
                    "expiration_date": "2026-07-01",
                    "strike": 150.0,
                    "option_type": "call",
                    "bid": 1.50,
                    "ask": 1.55,
                    "last": 1.52,
                    "volume": 100,
                    "open_interest": 500,
                    "implied_volatility": 0.25,
                    "greeks": None,
                    "underlying_price": 155.0,
                }
            ]
        }
    }
    chain = normalizer.normalize_chain("AAPL", date(2026, 7, 1), response)
    c = chain.contracts[0]
    assert c.greeks is not None
    assert c.greeks.source == GreeksSource.CALCULATED


def test_normalize_chain_no_greeks_when_no_iv(normalizer):
    response = {
        "options": {
            "option": [
                {
                    "symbol": "AAPL240119C00150000",
                    "strike": 150.0,
                    "option_type": "call",
                    "bid": None,
                    "ask": None,
                    "last": None,
                    "volume": None,
                    "open_interest": None,
                    "implied_volatility": None,
                    "greeks": None,
                }
            ]
        }
    }
    chain = normalizer.normalize_chain("AAPL", date(2024, 1, 19), response)
    assert chain.contracts[0].greeks is None


def test_normalize_expirations_single_date(normalizer):
    """Tradier returns a string (not list) when only one expiration."""
    response = {"expirations": {"date": "2024-01-19"}}
    result = normalizer.normalize_expirations(response)
    assert result == [date(2024, 1, 19)]
