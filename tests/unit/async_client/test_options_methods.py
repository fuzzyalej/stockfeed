"""Unit tests for AsyncStockFeedClient options methods."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stockfeed.async_client import AsyncStockFeedClient
from stockfeed.config import StockFeedSettings
from stockfeed.exceptions import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    TickerNotFoundError,
)
from stockfeed.models.options import (
    OptionChain,
    OptionContract,
    OptionQuote,
    OptionType,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 19, tzinfo=timezone.utc)
_EXP = date(2024, 1, 19)
_TICKER = "AAPL"
_SYMBOL = "AAPL240119C00150000"


def _contract() -> OptionContract:
    return OptionContract(
        symbol=_SYMBOL,
        underlying=_TICKER,
        expiration=_EXP,
        strike=Decimal("150"),
        option_type=OptionType.CALL,
        bid=Decimal("1.50"),
        ask=Decimal("1.55"),
        last=Decimal("1.52"),
        volume=500,
        open_interest=1000,
        implied_volatility=Decimal("0.25"),
        greeks=None,
        provider="tradier",
    )


def _chain() -> OptionChain:
    return OptionChain(
        underlying=_TICKER,
        expiration=_EXP,
        contracts=[_contract()],
        provider="tradier",
    )


def _option_quote() -> OptionQuote:
    return OptionQuote(
        symbol=_SYMBOL,
        underlying=_TICKER,
        timestamp=_TS,
        bid=Decimal("1.50"),
        ask=Decimal("1.55"),
        last=Decimal("1.52"),
        volume=500,
        open_interest=1000,
        implied_volatility=Decimal("0.25"),
        greeks=None,
        provider="tradier",
    )


def _make_provider(
    expirations=None,
    chain=None,
    quote=None,
    expirations_side_effect=None,
    chain_side_effect=None,
    quote_side_effect=None,
) -> MagicMock:
    """Build a mock provider with async options methods."""
    p = MagicMock()
    p.async_get_option_expirations = AsyncMock(
        return_value=expirations, side_effect=expirations_side_effect
    )
    p.async_get_options_chain = AsyncMock(return_value=chain, side_effect=chain_side_effect)
    p.async_get_option_quote = AsyncMock(return_value=quote, side_effect=quote_side_effect)
    return p


@pytest.fixture()
def client() -> AsyncStockFeedClient:
    settings = StockFeedSettings(cache_enabled=False)
    with patch("stockfeed.async_client.OptionsProviderSelector") as mock_sel_cls:
        mock_selector = MagicMock()
        mock_sel_cls.return_value = mock_selector
        c = AsyncStockFeedClient(settings=settings)
        # Expose selector mock for tests to configure
        c._options_selector = mock_selector
        return c


# ---------------------------------------------------------------------------
# get_option_expirations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_option_expirations_happy_path(client):
    """Returns the list from the first provider."""
    dates = [date(2024, 1, 19), date(2024, 2, 16)]
    p = _make_provider(expirations=dates)
    client._options_selector.select.return_value = [p]

    result = await client.get_option_expirations(_TICKER)

    assert result == dates
    p.async_get_option_expirations.assert_awaited_once_with(_TICKER)


@pytest.mark.asyncio
async def test_get_option_expirations_rate_limit_failover(client):
    """First provider raises RateLimitError; second returns successfully."""
    dates = [date(2024, 1, 19)]
    p1 = _make_provider(expirations_side_effect=ProviderRateLimitError("slow"))
    p2 = _make_provider(expirations=dates)
    client._options_selector.select.return_value = [p1, p2]

    result = await client.get_option_expirations(_TICKER)

    assert result == dates
    p1.async_get_option_expirations.assert_awaited_once()
    p2.async_get_option_expirations.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_option_expirations_ticker_not_found_reraises(client):
    """TickerNotFoundError is re-raised immediately without failover."""
    p = _make_provider(expirations_side_effect=TickerNotFoundError("AAPL"))
    client._options_selector.select.return_value = [p]

    with pytest.raises(TickerNotFoundError):
        await client.get_option_expirations(_TICKER)


@pytest.mark.asyncio
async def test_get_option_expirations_not_implemented_skips(client):
    """NotImplementedError causes the provider to be skipped."""
    dates = [date(2024, 1, 19)]
    p1 = _make_provider(expirations_side_effect=NotImplementedError)
    p2 = _make_provider(expirations=dates)
    client._options_selector.select.return_value = [p1, p2]

    result = await client.get_option_expirations(_TICKER)

    assert result == dates


@pytest.mark.asyncio
async def test_get_option_expirations_all_exhausted(client):
    """Raises ProviderUnavailableError when all providers fail."""
    p = _make_provider(expirations_side_effect=ProviderUnavailableError("down", ticker=_TICKER))
    client._options_selector.select.return_value = [p]

    with pytest.raises(ProviderUnavailableError):
        await client.get_option_expirations(_TICKER)


# ---------------------------------------------------------------------------
# get_options_chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_options_chain_happy_path(client):
    """Returns the chain from the first provider."""
    chain = _chain()
    p = _make_provider(chain=chain)
    client._options_selector.select.return_value = [p]

    result = await client.get_options_chain(_TICKER, _EXP)

    assert result == chain
    p.async_get_options_chain.assert_awaited_once_with(_TICKER, _EXP)


@pytest.mark.asyncio
async def test_get_options_chain_rate_limit_failover(client):
    """First provider rate-limited; second succeeds."""
    chain = _chain()
    p1 = _make_provider(chain_side_effect=ProviderRateLimitError("slow"))
    p2 = _make_provider(chain=chain)
    client._options_selector.select.return_value = [p1, p2]

    result = await client.get_options_chain(_TICKER, _EXP)

    assert result == chain


@pytest.mark.asyncio
async def test_get_options_chain_ticker_not_found_reraises(client):
    """TickerNotFoundError is re-raised immediately."""
    p = _make_provider(chain_side_effect=TickerNotFoundError("AAPL"))
    client._options_selector.select.return_value = [p]

    with pytest.raises(TickerNotFoundError):
        await client.get_options_chain(_TICKER, _EXP)


@pytest.mark.asyncio
async def test_get_options_chain_not_implemented_skips(client):
    """NotImplementedError skips to next provider."""
    chain = _chain()
    p1 = _make_provider(chain_side_effect=NotImplementedError)
    p2 = _make_provider(chain=chain)
    client._options_selector.select.return_value = [p1, p2]

    result = await client.get_options_chain(_TICKER, _EXP)

    assert result == chain


@pytest.mark.asyncio
async def test_get_options_chain_all_exhausted(client):
    """Raises ProviderUnavailableError when all providers fail."""
    p = _make_provider(chain_side_effect=ProviderUnavailableError("down", ticker=_TICKER))
    client._options_selector.select.return_value = [p]

    with pytest.raises(ProviderUnavailableError):
        await client.get_options_chain(_TICKER, _EXP)


# ---------------------------------------------------------------------------
# get_option_quote
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_option_quote_happy_path(client):
    """Returns the quote from the first provider."""
    oq = _option_quote()
    p = _make_provider(quote=oq)
    client._options_selector.select.return_value = [p]

    result = await client.get_option_quote(_SYMBOL)

    assert result == oq
    p.async_get_option_quote.assert_awaited_once_with(_SYMBOL)


@pytest.mark.asyncio
async def test_get_option_quote_rate_limit_failover(client):
    """First provider rate-limited; second succeeds."""
    oq = _option_quote()
    p1 = _make_provider(quote_side_effect=ProviderRateLimitError("slow"))
    p2 = _make_provider(quote=oq)
    client._options_selector.select.return_value = [p1, p2]

    result = await client.get_option_quote(_SYMBOL)

    assert result == oq


@pytest.mark.asyncio
async def test_get_option_quote_auth_error_reraises(client):
    """ProviderAuthError is re-raised immediately."""
    p = _make_provider(quote_side_effect=ProviderAuthError("bad key"))
    client._options_selector.select.return_value = [p]

    with pytest.raises(ProviderAuthError):
        await client.get_option_quote(_SYMBOL)


@pytest.mark.asyncio
async def test_get_option_quote_not_implemented_skips(client):
    """NotImplementedError skips to next provider."""
    oq = _option_quote()
    p1 = _make_provider(quote_side_effect=NotImplementedError)
    p2 = _make_provider(quote=oq)
    client._options_selector.select.return_value = [p1, p2]

    result = await client.get_option_quote(_SYMBOL)

    assert result == oq


@pytest.mark.asyncio
async def test_get_option_quote_all_exhausted(client):
    """Raises ProviderUnavailableError when all providers fail."""
    p = _make_provider(quote_side_effect=ProviderUnavailableError("down"))
    client._options_selector.select.return_value = [p]

    with pytest.raises(ProviderUnavailableError):
        await client.get_option_quote(_SYMBOL)
