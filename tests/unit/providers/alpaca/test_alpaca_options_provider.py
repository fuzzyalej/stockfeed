"""Unit tests for AlpacaProvider options methods."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from stockfeed.models.options import OptionChain, OptionQuote
from stockfeed.providers.alpaca.provider import AlpacaProvider


@pytest.fixture()
def provider() -> AlpacaProvider:
    return AlpacaProvider(api_key="test-key", secret_key="test-secret")


def _make_client_mock(json_pages: list[dict]) -> MagicMock:
    """Build a context-manager mock that returns successive JSON responses."""
    responses = [MagicMock(status_code=200) for _ in json_pages]
    for resp, data in zip(responses, json_pages, strict=False):
        resp.json.return_value = data
    client = MagicMock()
    client.get.side_effect = responses
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# get_option_expirations
# ---------------------------------------------------------------------------

EXPIRY_RESPONSE_SINGLE_PAGE = {
    "option_contracts": [
        {"symbol": "AAPL240119C00150000", "expiration_date": "2024-01-19", "type": "call"},
        {"symbol": "AAPL240119P00150000", "expiration_date": "2024-01-19", "type": "put"},
        {"symbol": "AAPL240216C00155000", "expiration_date": "2024-02-16", "type": "call"},
    ],
    "next_page_token": None,
}


def test_get_option_expirations_returns_sorted_unique_dates(provider: AlpacaProvider) -> None:
    client_mock = _make_client_mock([EXPIRY_RESPONSE_SINGLE_PAGE])
    with patch.object(provider, "_client", return_value=client_mock):
        result = provider.get_option_expirations("AAPL")

    assert result == [date(2024, 1, 19), date(2024, 2, 16)]


def test_get_option_expirations_paginates(provider: AlpacaProvider) -> None:
    page1 = {
        "option_contracts": [
            {"symbol": "AAPL240119C00150000", "expiration_date": "2024-01-19", "type": "call"},
        ],
        "next_page_token": "tok1",
    }
    page2 = {
        "option_contracts": [
            {"symbol": "AAPL240216C00155000", "expiration_date": "2024-02-16", "type": "call"},
        ],
        "next_page_token": None,
    }
    client_mock = _make_client_mock([page1, page2])
    with patch.object(provider, "_client", return_value=client_mock):
        result = provider.get_option_expirations("AAPL")

    assert len(result) == 2
    assert client_mock.get.call_count == 2


# ---------------------------------------------------------------------------
# get_options_chain
# ---------------------------------------------------------------------------

SNAPSHOT_ENTRY = {
    "latestQuote": {"ap": 5.10, "bp": 4.90, "as": 10, "bs": 5},
    "latestTrade": {"p": 5.00, "s": 3},
    "greeks": {"delta": 0.52, "gamma": 0.03, "theta": -0.08, "vega": 0.12, "rho": 0.05},
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

CHAIN_RESPONSE = {
    "snapshots": {"AAPL240119C00150000": SNAPSHOT_ENTRY},
    "next_page_token": None,
}


def test_get_options_chain_returns_option_chain(provider: AlpacaProvider) -> None:
    client_mock = _make_client_mock([CHAIN_RESPONSE])
    with patch.object(provider, "_client", return_value=client_mock):
        result = provider.get_options_chain("AAPL", date(2024, 1, 19))

    assert isinstance(result, OptionChain)
    assert result.underlying == "AAPL"
    assert result.expiration == date(2024, 1, 19)
    assert result.provider == "alpaca"
    assert len(result.contracts) == 1


def test_get_options_chain_paginates(provider: AlpacaProvider) -> None:
    page1 = {
        "snapshots": {"AAPL240119C00150000": SNAPSHOT_ENTRY},
        "next_page_token": "tok1",
    }
    page2_entry = dict(SNAPSHOT_ENTRY)
    page2_entry = {
        **SNAPSHOT_ENTRY,
        "details": {**SNAPSHOT_ENTRY["details"], "symbol": "AAPL240119P00150000", "type": "put"},
    }
    page2 = {
        "snapshots": {"AAPL240119P00150000": page2_entry},
        "next_page_token": None,
    }
    client_mock = _make_client_mock([page1, page2])
    with patch.object(provider, "_client", return_value=client_mock):
        result = provider.get_options_chain("AAPL", date(2024, 1, 19))

    assert len(result.contracts) == 2
    assert client_mock.get.call_count == 2


# ---------------------------------------------------------------------------
# get_option_quote
# ---------------------------------------------------------------------------

QUOTE_RESPONSE = {
    "snapshots": {"AAPL240119C00150000": SNAPSHOT_ENTRY},
    "next_page_token": None,
}


def test_get_option_quote_returns_option_quote(provider: AlpacaProvider) -> None:
    client_mock = _make_client_mock([QUOTE_RESPONSE])
    with patch.object(provider, "_client", return_value=client_mock):
        result = provider.get_option_quote("AAPL240119C00150000")

    assert isinstance(result, OptionQuote)
    assert result.symbol == "AAPL240119C00150000"
    assert result.provider == "alpaca"


def test_get_option_quote_raises_on_invalid_symbol(provider: AlpacaProvider) -> None:
    with pytest.raises(ValueError, match="Cannot parse OCC symbol"):
        provider.get_option_quote("INVALID")


# ---------------------------------------------------------------------------
# is_options_capable
# ---------------------------------------------------------------------------


def test_alpaca_provider_is_options_capable() -> None:
    from stockfeed.providers.base_options import AbstractOptionsProvider

    assert issubclass(AlpacaProvider, AbstractOptionsProvider)
