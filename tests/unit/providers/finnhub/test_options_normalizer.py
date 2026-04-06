"""Tests for FinnhubOptionsNormalizer and Finnhub provider options methods."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from stockfeed.exceptions import TickerNotFoundError
from stockfeed.models.options import GreeksSource, OptionType
from stockfeed.providers.finnhub.options_normalizer import FinnhubOptionsNormalizer

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

EXPIRATION = date(2027, 6, 20)
EXPIRATION_STR = "2027-06-20"
OTHER_EXPIRATION_STR = "2027-07-18"

SAMPLE_CALL = {
    "contractName": "AAPL270620C00150000",
    "contractSize": "REGULAR",
    "currency": "USD",
    "inTheMoney": True,
    "lastTradeDate": "2027-06-10T14:32:00+00:00",
    "strike": 150.0,
    "lastPrice": 5.10,
    "bid": 4.90,
    "ask": 5.20,
    "change": 0.30,
    "percentChange": 6.25,
    "volume": 150,
    "openInterest": 1200,
    "impliedVolatility": 0.25,
}

SAMPLE_PUT = {
    "contractName": "AAPL270620P00150000",
    "contractSize": "REGULAR",
    "currency": "USD",
    "inTheMoney": False,
    "lastTradeDate": "2027-06-10T12:00:00+00:00",
    "strike": 150.0,
    "lastPrice": 3.50,
    "bid": 3.40,
    "ask": 3.60,
    "change": -0.10,
    "percentChange": -2.78,
    "volume": 80,
    "openInterest": 600,
    "impliedVolatility": 0.22,
}

SAMPLE_OTHER_CALL = {
    "contractName": "AAPL270718C00155000",
    "contractSize": "REGULAR",
    "currency": "USD",
    "inTheMoney": False,
    "lastTradeDate": "2027-07-10T14:32:00+00:00",
    "strike": 155.0,
    "lastPrice": 4.00,
    "bid": 3.90,
    "ask": 4.10,
    "change": 0.10,
    "percentChange": 2.56,
    "volume": 200,
    "openInterest": 900,
    "impliedVolatility": 0.28,
}


def make_raw_response(
    include_target_expiration: bool = True,
    include_other_expiration: bool = False,
    call_iv: float | None = 0.25,
    put_iv: float | None = 0.22,
) -> dict:
    """Build a Finnhub-style option chain API response."""
    data_blocks = []

    if include_target_expiration:
        call = {**SAMPLE_CALL}
        put = {**SAMPLE_PUT}
        if call_iv is None:
            call.pop("impliedVolatility", None)
        else:
            call["impliedVolatility"] = call_iv
        if put_iv is None:
            put.pop("impliedVolatility", None)
        else:
            put["impliedVolatility"] = put_iv

        data_blocks.append(
            {
                "expirationDate": EXPIRATION_STR,
                "options": {
                    "CALL": [call],
                    "PUT": [put],
                },
            }
        )

    if include_other_expiration:
        data_blocks.append(
            {
                "expirationDate": OTHER_EXPIRATION_STR,
                "options": {
                    "CALL": [SAMPLE_OTHER_CALL],
                    "PUT": [],
                },
            }
        )

    return {"code": "AAPL", "exchange": "US", "data": data_blocks}


@pytest.fixture()
def normalizer() -> FinnhubOptionsNormalizer:
    return FinnhubOptionsNormalizer(risk_free_rate=Decimal("0.05"))


# ---------------------------------------------------------------------------
# normalize_chain — basic structure
# ---------------------------------------------------------------------------


def test_normalize_chain_returns_option_chain(normalizer: FinnhubOptionsNormalizer) -> None:
    raw = make_raw_response()
    chain = normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=Decimal("160"))

    assert chain.underlying == "AAPL"
    assert chain.expiration == EXPIRATION
    assert chain.provider == "finnhub"


def test_normalize_chain_has_calls_and_puts(normalizer: FinnhubOptionsNormalizer) -> None:
    raw = make_raw_response()
    chain = normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=Decimal("160"))

    call_contracts = [c for c in chain.contracts if c.option_type == OptionType.CALL]
    put_contracts = [c for c in chain.contracts if c.option_type == OptionType.PUT]

    assert len(call_contracts) == 1
    assert len(put_contracts) == 1


def test_normalize_chain_contract_fields(normalizer: FinnhubOptionsNormalizer) -> None:
    raw = make_raw_response()
    chain = normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=Decimal("160"))

    call = next(c for c in chain.contracts if c.option_type == OptionType.CALL)
    assert call.symbol == "AAPL270620C00150000"
    assert call.underlying == "AAPL"
    assert call.expiration == EXPIRATION
    assert call.strike == Decimal("150.0")
    assert call.bid == Decimal("4.9")
    assert call.ask == Decimal("5.2")
    assert call.last == Decimal("5.1")
    assert call.volume == 150
    assert call.open_interest == 1200
    assert call.provider == "finnhub"


# ---------------------------------------------------------------------------
# normalize_chain — expiration filtering
# ---------------------------------------------------------------------------


def test_normalize_chain_filters_to_target_expiration(
    normalizer: FinnhubOptionsNormalizer,
) -> None:
    """Only contracts from the requested expiration date are returned."""
    raw = make_raw_response(include_target_expiration=True, include_other_expiration=True)
    chain = normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=Decimal("160"))

    # Should only have contracts from EXPIRATION (1 call + 1 put), not from the other date
    assert len(chain.contracts) == 2
    for contract in chain.contracts:
        assert contract.expiration == EXPIRATION


def test_normalize_chain_raises_when_expiration_not_found(
    normalizer: FinnhubOptionsNormalizer,
) -> None:
    """TickerNotFoundError raised when no data block matches the expiration."""
    raw = make_raw_response(include_target_expiration=False, include_other_expiration=True)

    with pytest.raises(TickerNotFoundError):
        normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=Decimal("160"))


def test_normalize_chain_raises_when_data_empty(normalizer: FinnhubOptionsNormalizer) -> None:
    """TickerNotFoundError raised when data list is empty."""
    raw = {"code": "AAPL", "exchange": "US", "data": []}

    with pytest.raises(TickerNotFoundError):
        normalizer.normalize_chain("AAPL", EXPIRATION, raw)


# ---------------------------------------------------------------------------
# normalize_chain — greeks calculation
# ---------------------------------------------------------------------------


def test_greeks_calculated_when_iv_and_price_available(
    normalizer: FinnhubOptionsNormalizer,
) -> None:
    raw = make_raw_response()
    chain = normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=Decimal("160"))

    for contract in chain.contracts:
        assert contract.greeks is not None
        assert contract.greeks.source == GreeksSource.CALCULATED


def test_greeks_none_when_no_implied_volatility(normalizer: FinnhubOptionsNormalizer) -> None:
    raw = make_raw_response(call_iv=None, put_iv=None)
    chain = normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=Decimal("160"))

    for contract in chain.contracts:
        assert contract.greeks is None


def test_greeks_none_when_no_underlying_price(normalizer: FinnhubOptionsNormalizer) -> None:
    raw = make_raw_response()
    chain = normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=None)

    for contract in chain.contracts:
        assert contract.greeks is None


def test_greeks_source_is_calculated(normalizer: FinnhubOptionsNormalizer) -> None:
    raw = make_raw_response()
    chain = normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=Decimal("160"))

    for contract in chain.contracts:
        assert contract.greeks is not None
        assert contract.greeks.source == GreeksSource.CALCULATED


def test_call_greeks_delta_positive(normalizer: FinnhubOptionsNormalizer) -> None:
    """Call delta should be positive (between 0 and 1)."""
    raw = make_raw_response()
    chain = normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=Decimal("160"))

    call = next(c for c in chain.contracts if c.option_type == OptionType.CALL)
    assert call.greeks is not None
    assert call.greeks.delta is not None
    assert Decimal("0") < call.greeks.delta <= Decimal("1")


def test_put_greeks_delta_negative(normalizer: FinnhubOptionsNormalizer) -> None:
    """Put delta should be negative (between -1 and 0)."""
    raw = make_raw_response()
    chain = normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=Decimal("160"))

    put = next(c for c in chain.contracts if c.option_type == OptionType.PUT)
    assert put.greeks is not None
    assert put.greeks.delta is not None
    assert Decimal("-1") <= put.greeks.delta < Decimal("0")


# ---------------------------------------------------------------------------
# Provider-level NotImplementedError tests
# ---------------------------------------------------------------------------


def test_provider_get_option_expirations_raises() -> None:
    from stockfeed.providers.finnhub.provider import FinnhubProvider

    provider = FinnhubProvider(api_key="test-key")
    with pytest.raises(NotImplementedError):
        provider.get_option_expirations("AAPL")


def test_provider_get_option_quote_raises() -> None:
    from stockfeed.providers.finnhub.provider import FinnhubProvider

    provider = FinnhubProvider(api_key="test-key")
    with pytest.raises(NotImplementedError):
        provider.get_option_quote("AAPL250620C00150000")


@pytest.mark.asyncio
async def test_provider_async_get_option_expirations_raises() -> None:
    from stockfeed.providers.finnhub.provider import FinnhubProvider

    provider = FinnhubProvider(api_key="test-key")
    with pytest.raises(NotImplementedError):
        await provider.async_get_option_expirations("AAPL")


@pytest.mark.asyncio
async def test_provider_async_get_option_quote_raises() -> None:
    from stockfeed.providers.finnhub.provider import FinnhubProvider

    provider = FinnhubProvider(api_key="test-key")
    with pytest.raises(NotImplementedError):
        await provider.async_get_option_quote("AAPL270620C00150000")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_underlying_uppercase(normalizer: FinnhubOptionsNormalizer) -> None:
    raw = make_raw_response()
    chain = normalizer.normalize_chain("aapl", EXPIRATION, raw, underlying_price=Decimal("160"))

    assert chain.underlying == "AAPL"
    for contract in chain.contracts:
        assert contract.underlying == "AAPL"


def test_none_volume_and_open_interest(normalizer: FinnhubOptionsNormalizer) -> None:
    raw = make_raw_response()
    # Remove volume and openInterest from first call contract
    raw["data"][0]["options"]["CALL"][0].pop("volume")
    raw["data"][0]["options"]["CALL"][0].pop("openInterest")

    chain = normalizer.normalize_chain("AAPL", EXPIRATION, raw, underlying_price=Decimal("160"))
    call = next(c for c in chain.contracts if c.option_type == OptionType.CALL)

    assert call.volume is None
    assert call.open_interest is None
