from datetime import date, datetime, timezone
from decimal import Decimal

from stockfeed.models.options import (
    Greeks,
    GreeksSource,
    OptionChain,
    OptionContract,
    OptionQuote,
    OptionType,
)


def test_greeks_source_values():
    assert GreeksSource.API == "api"
    assert GreeksSource.CALCULATED == "calculated"


def test_greeks_model():
    g = Greeks(
        delta=Decimal("0.5"),
        gamma=Decimal("0.02"),
        theta=Decimal("-0.05"),
        vega=Decimal("0.1"),
        rho=Decimal("0.01"),
        source=GreeksSource.API,
    )
    assert g.source == GreeksSource.API
    assert g.delta == Decimal("0.5")


def test_greeks_all_none_except_source():
    g = Greeks(
        delta=None, gamma=None, theta=None, vega=None, rho=None, source=GreeksSource.CALCULATED
    )
    assert g.delta is None


def test_option_contract_ticker_uppercased():
    c = OptionContract(
        symbol="AAPL240119C00150000",
        underlying="aapl",
        expiration=date(2024, 1, 19),
        strike=Decimal("150"),
        option_type=OptionType.CALL,
        bid=Decimal("1.50"),
        ask=Decimal("1.55"),
        last=Decimal("1.52"),
        volume=100,
        open_interest=500,
        implied_volatility=Decimal("0.25"),
        greeks=None,
        provider="yfinance",
    )
    assert c.underlying == "AAPL"


def test_option_chain_model():
    chain = OptionChain(
        underlying="AAPL",
        expiration=date(2024, 1, 19),
        contracts=[],
        provider="yfinance",
    )
    assert chain.contracts == []


def test_option_quote_model():
    q = OptionQuote(
        symbol="AAPL240119C00150000",
        underlying="AAPL",
        bid=Decimal("1.50"),
        ask=Decimal("1.55"),
        last=Decimal("1.52"),
        volume=100,
        open_interest=500,
        implied_volatility=Decimal("0.25"),
        greeks=None,
        timestamp=datetime.now(timezone.utc),
        provider="yfinance",
    )
    assert q.symbol == "AAPL240119C00150000"
