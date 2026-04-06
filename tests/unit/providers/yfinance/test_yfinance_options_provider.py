from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from stockfeed.models.options import OptionChain, OptionType
from stockfeed.providers.base_options import AbstractOptionsProvider
from stockfeed.providers.yfinance.provider import YFinanceProvider


def test_yfinance_provider_is_options_capable():
    assert issubclass(YFinanceProvider, AbstractOptionsProvider)


@patch("stockfeed.providers.yfinance.provider.yf.Ticker")
def test_get_option_expirations(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.options = ("2024-01-19", "2024-03-15")
    mock_ticker_cls.return_value = mock_ticker

    provider = YFinanceProvider()
    result = provider.get_option_expirations("AAPL")
    assert result == [date(2024, 1, 19), date(2024, 3, 15)]


@patch("stockfeed.providers.yfinance.provider.yf.Ticker")
def test_get_options_chain(mock_ticker_cls):
    mock_ticker = MagicMock()
    mock_ticker.fast_info = {"lastPrice": 155.0}

    calls_df = pd.DataFrame(
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
    puts_df = pd.DataFrame()

    chain_mock = MagicMock()
    chain_mock.calls = calls_df
    chain_mock.puts = puts_df
    mock_ticker.option_chain.return_value = chain_mock
    mock_ticker_cls.return_value = mock_ticker

    provider = YFinanceProvider()
    result = provider.get_options_chain("AAPL", date(2026, 7, 1))
    assert isinstance(result, OptionChain)
    assert result.underlying == "AAPL"
    assert len(result.contracts) == 1
    assert result.contracts[0].option_type == OptionType.CALL


@patch("stockfeed.providers.yfinance.provider.yf.Ticker")
def test_get_option_quote(mock_ticker_cls):
    mock_ticker = MagicMock()
    calls_df = pd.DataFrame(
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
    chain_mock = MagicMock()
    chain_mock.calls = calls_df
    chain_mock.puts = pd.DataFrame()
    mock_ticker.option_chain.return_value = chain_mock
    mock_ticker_cls.return_value = mock_ticker

    provider = YFinanceProvider()
    result = provider.get_option_quote("AAPL260701C00150000")
    assert result.symbol == "AAPL260701C00150000"
    assert result.provider == "yfinance"
