from datetime import date
from unittest.mock import MagicMock, patch

from stockfeed.models.options import OptionChain
from stockfeed.providers.base_options import AbstractOptionsProvider
from stockfeed.providers.tradier.provider import TradierProvider


def test_tradier_provider_is_options_capable():
    assert issubclass(TradierProvider, AbstractOptionsProvider)


@patch("stockfeed.providers.tradier.provider.httpx.Client")
def test_get_option_expirations(mock_client_cls):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"expirations": {"date": ["2024-01-19", "2024-03-15"]}}
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    provider = TradierProvider(api_key="test")
    result = provider.get_option_expirations("AAPL")
    assert result == [date(2024, 1, 19), date(2024, 3, 15)]
    mock_client.get.assert_called_once_with(
        "/v1/markets/options/expirations",
        params={"symbol": "AAPL"},
    )


@patch("stockfeed.providers.tradier.provider.httpx.Client")
def test_get_options_chain(mock_client_cls):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
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
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp
    mock_client_cls.return_value = mock_client

    provider = TradierProvider(api_key="test")
    result = provider.get_options_chain("AAPL", date(2024, 1, 19))
    assert isinstance(result, OptionChain)
    assert len(result.contracts) == 1
    assert result.contracts[0].greeks is not None
    mock_client.get.assert_called_once_with(
        "/v1/markets/options/chains",
        params={"symbol": "AAPL", "expiration": "2024-01-19", "greeks": "true"},
    )
