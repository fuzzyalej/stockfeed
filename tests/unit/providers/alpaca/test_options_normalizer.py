"""Unit tests for AlpacaOptionsNormalizer."""

from datetime import date
from decimal import Decimal

import pytest

from stockfeed.models.options import GreeksSource, OptionType
from stockfeed.providers.alpaca.options_normalizer import AlpacaOptionsNormalizer


@pytest.fixture
def normalizer():
    return AlpacaOptionsNormalizer(risk_free_rate=Decimal("0.05"))


# ---------------------------------------------------------------------------
# normalize_expirations
# ---------------------------------------------------------------------------


def test_normalize_expirations_empty(normalizer):
    result = normalizer.normalize_expirations({"option_contracts": []})
    assert result == []


def test_normalize_expirations_missing_key(normalizer):
    result = normalizer.normalize_expirations({})
    assert result == []


def test_normalize_expirations_single(normalizer):
    raw = {
        "option_contracts": [
            {
                "symbol": "AAPL240119C00150000",
                "underlying_symbol": "AAPL",
                "expiration_date": "2024-01-19",
                "strike_price": "150.0",
                "type": "call",
            }
        ],
        "next_page_token": None,
    }
    result = normalizer.normalize_expirations(raw)
    assert result == [date(2024, 1, 19)]


def test_normalize_expirations_multiple_deduplicated_and_sorted(normalizer):
    raw = {
        "option_contracts": [
            {"expiration_date": "2024-03-15", "symbol": "AAPL240315C00150000"},
            {"expiration_date": "2024-01-19", "symbol": "AAPL240119C00150000"},
            {"expiration_date": "2024-01-19", "symbol": "AAPL240119P00150000"},
            {"expiration_date": "2024-06-21", "symbol": "AAPL240621C00150000"},
        ],
        "next_page_token": None,
    }
    result = normalizer.normalize_expirations(raw)
    assert result == [date(2024, 1, 19), date(2024, 3, 15), date(2024, 6, 21)]


# ---------------------------------------------------------------------------
# normalize_chain
# ---------------------------------------------------------------------------

_CALL_SNAPSHOT_WITH_API_GREEKS = {
    "AAPL240119C00150000": {
        "latestQuote": {"ap": 5.10, "bp": 4.90, "as": 10, "bs": 5},
        "latestTrade": {"p": 5.00, "s": 3},
        "greeks": {
            "delta": 0.52,
            "gamma": 0.03,
            "theta": -0.08,
            "vega": 0.12,
            "rho": 0.05,
        },
        "impliedVolatility": 0.25,
        "details": {
            "symbol": "AAPL240119C00150000",
            "underlyingSymbol": "AAPL",
            "expirationDate": "2024-01-19",
            "strikePrice": "150.0",
            "type": "call",
            "openInterest": 1000,
        },
    }
}

_PUT_SNAPSHOT_WITH_API_GREEKS = {
    "AAPL240119P00150000": {
        "latestQuote": {"ap": 1.20, "bp": 1.10, "as": 5, "bs": 3},
        "latestTrade": {"p": 1.15, "s": 2},
        "greeks": {
            "delta": -0.48,
            "gamma": 0.03,
            "theta": -0.07,
            "vega": 0.11,
            "rho": -0.04,
        },
        "impliedVolatility": 0.27,
        "details": {
            "symbol": "AAPL240119P00150000",
            "underlyingSymbol": "AAPL",
            "expirationDate": "2024-01-19",
            "strikePrice": "150.0",
            "type": "put",
            "openInterest": 800,
        },
    }
}

_SNAPSHOT_IV_NO_GREEKS = {
    "AAPL260701C00150000": {
        "latestQuote": {"ap": 10.50, "bp": 10.20, "as": 5, "bs": 3},
        "latestTrade": {"p": 10.35, "s": 1},
        "greeks": None,
        "impliedVolatility": 0.25,
        "underlyingPrice": 155.0,
        "details": {
            "symbol": "AAPL260701C00150000",
            "underlyingSymbol": "AAPL",
            "expirationDate": "2026-07-01",
            "strikePrice": "150.0",
            "type": "call",
            "openInterest": 500,
        },
    }
}

_SNAPSHOT_NO_IV_NO_GREEKS = {
    "AAPL240119C00200000": {
        "latestQuote": {"ap": None, "bp": None, "as": 0, "bs": 0},
        "latestTrade": {"p": None, "s": 0},
        "greeks": None,
        "impliedVolatility": None,
        "details": {
            "symbol": "AAPL240119C00200000",
            "underlyingSymbol": "AAPL",
            "expirationDate": "2024-01-19",
            "strikePrice": "200.0",
            "type": "call",
            "openInterest": 0,
        },
    }
}


def test_normalize_chain_call_with_api_greeks(normalizer):
    chain = normalizer.normalize_chain("AAPL", date(2024, 1, 19), _CALL_SNAPSHOT_WITH_API_GREEKS)
    assert chain.underlying == "AAPL"
    assert chain.expiration == date(2024, 1, 19)
    assert chain.provider == "alpaca"
    assert len(chain.contracts) == 1

    c = chain.contracts[0]
    assert c.symbol == "AAPL240119C00150000"
    assert c.option_type == OptionType.CALL
    assert c.strike == Decimal("150.0")
    assert c.bid == Decimal("4.9")
    assert c.ask == Decimal("5.1")
    assert c.last == Decimal("5.0")
    assert c.open_interest == 1000
    assert c.greeks is not None
    assert c.greeks.source == GreeksSource.API
    assert c.greeks.delta == Decimal("0.52")
    assert c.greeks.gamma == Decimal("0.03")
    assert c.greeks.theta == Decimal("-0.08")
    assert c.greeks.vega == Decimal("0.12")
    assert c.greeks.rho == Decimal("0.05")


def test_normalize_chain_put_with_api_greeks(normalizer):
    chain = normalizer.normalize_chain("AAPL", date(2024, 1, 19), _PUT_SNAPSHOT_WITH_API_GREEKS)
    assert len(chain.contracts) == 1
    c = chain.contracts[0]
    assert c.option_type == OptionType.PUT
    assert c.greeks is not None
    assert c.greeks.source == GreeksSource.API
    assert c.greeks.delta == Decimal("-0.48")


def test_normalize_chain_mixed_call_and_put(normalizer):
    merged = {}
    merged.update(_CALL_SNAPSHOT_WITH_API_GREEKS)
    merged.update(_PUT_SNAPSHOT_WITH_API_GREEKS)
    chain = normalizer.normalize_chain("AAPL", date(2024, 1, 19), merged)
    assert len(chain.contracts) == 2
    types = {c.option_type for c in chain.contracts}
    assert types == {OptionType.CALL, OptionType.PUT}


def test_normalize_chain_iv_present_no_api_greeks_uses_calculated(normalizer):
    chain = normalizer.normalize_chain("AAPL", date(2026, 7, 1), _SNAPSHOT_IV_NO_GREEKS)
    assert len(chain.contracts) == 1
    c = chain.contracts[0]
    assert c.greeks is not None
    assert c.greeks.source == GreeksSource.CALCULATED


def test_normalize_chain_no_iv_no_greeks_returns_none(normalizer):
    chain = normalizer.normalize_chain("AAPL", date(2024, 1, 19), _SNAPSHOT_NO_IV_NO_GREEKS)
    assert len(chain.contracts) == 1
    assert chain.contracts[0].greeks is None


def test_normalize_chain_empty_snapshots(normalizer):
    chain = normalizer.normalize_chain("AAPL", date(2024, 1, 19), {})
    assert chain.contracts == []


# ---------------------------------------------------------------------------
# normalize_option_quote
# ---------------------------------------------------------------------------

_SINGLE_SNAPSHOT_API_GREEKS = {
    "latestQuote": {"ap": 5.10, "bp": 4.90, "as": 10, "bs": 5},
    "latestTrade": {"p": 5.00, "s": 3},
    "greeks": {
        "delta": 0.52,
        "gamma": 0.03,
        "theta": -0.08,
        "vega": 0.12,
        "rho": 0.05,
    },
    "impliedVolatility": 0.25,
    "details": {
        "symbol": "AAPL240119C00150000",
        "underlyingSymbol": "AAPL",
        "expirationDate": "2024-01-19",
        "strikePrice": "150.0",
        "type": "call",
        "openInterest": 1000,
    },
}

_SINGLE_SNAPSHOT_CALCULATED_GREEKS = {
    "latestQuote": {"ap": 10.50, "bp": 10.20, "as": 5, "bs": 3},
    "latestTrade": {"p": 10.35, "s": 1},
    "greeks": None,
    "impliedVolatility": 0.25,
    "underlyingPrice": 155.0,
    "details": {
        "symbol": "AAPL260701C00150000",
        "underlyingSymbol": "AAPL",
        "expirationDate": "2026-07-01",
        "strikePrice": "150.0",
        "type": "call",
        "openInterest": 500,
    },
}

_SINGLE_SNAPSHOT_NO_GREEKS = {
    "latestQuote": {"ap": None, "bp": None},
    "latestTrade": {"p": None, "s": 0},
    "greeks": None,
    "impliedVolatility": None,
    "details": {
        "symbol": "AAPL240119C00200000",
        "underlyingSymbol": "AAPL",
        "expirationDate": "2024-01-19",
        "strikePrice": "200.0",
        "type": "call",
        "openInterest": 0,
    },
}


def test_normalize_option_quote_with_api_greeks(normalizer):
    quote = normalizer.normalize_option_quote("AAPL240119C00150000", _SINGLE_SNAPSHOT_API_GREEKS)
    assert quote.symbol == "AAPL240119C00150000"
    assert quote.underlying == "AAPL"
    assert quote.provider == "alpaca"
    assert quote.bid == Decimal("4.9")
    assert quote.ask == Decimal("5.1")
    assert quote.last == Decimal("5.0")
    assert quote.open_interest == 1000
    assert quote.greeks is not None
    assert quote.greeks.source == GreeksSource.API
    assert quote.greeks.delta == Decimal("0.52")


def test_normalize_option_quote_with_calculated_greeks(normalizer):
    quote = normalizer.normalize_option_quote(
        "AAPL260701C00150000", _SINGLE_SNAPSHOT_CALCULATED_GREEKS
    )
    assert quote.greeks is not None
    assert quote.greeks.source == GreeksSource.CALCULATED


def test_normalize_option_quote_with_no_greeks(normalizer):
    quote = normalizer.normalize_option_quote("AAPL240119C00200000", _SINGLE_SNAPSHOT_NO_GREEKS)
    assert quote.greeks is None
    assert quote.implied_volatility is None


def test_normalize_option_quote_timestamp_is_set(normalizer):
    quote = normalizer.normalize_option_quote("AAPL240119C00150000", _SINGLE_SNAPSHOT_API_GREEKS)
    assert quote.timestamp is not None
