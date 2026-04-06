"""Unit tests for StockFeedClient options methods."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from stockfeed.exceptions import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    TickerNotFoundError,
)
from stockfeed.models.options import OptionChain, OptionQuote

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client():
    """Return a StockFeedClient with _options_selector mocked out."""
    with (
        patch("stockfeed.client.CacheManager"),
        patch("stockfeed.client.RateLimiter"),
        patch("stockfeed.client.HealthChecker"),
        patch("stockfeed.client.ProviderSelector"),
        patch("stockfeed.client.OptionsProviderSelector"),
    ):
        from stockfeed.client import StockFeedClient

        client = StockFeedClient()
        return client


def _mock_provider():
    p = MagicMock()
    p.name = "mock_provider"
    return p


def _sample_chain(ticker: str = "AAPL", exp: date = date(2024, 1, 19)) -> OptionChain:
    return OptionChain(underlying=ticker, expiration=exp, contracts=[], provider="mock")


def _sample_quote(symbol: str = "AAPL240119C00150000") -> OptionQuote:
    return OptionQuote(
        symbol=symbol,
        underlying="AAPL",
        timestamp=datetime(2024, 1, 10, 15, 0, tzinfo=timezone.utc),
        bid=Decimal("1.50"),
        ask=Decimal("1.55"),
        last=Decimal("1.52"),
        volume=100,
        open_interest=200,
        implied_volatility=Decimal("0.30"),
        greeks=None,
        provider="mock",
    )


# ---------------------------------------------------------------------------
# get_option_expirations
# ---------------------------------------------------------------------------


class TestGetOptionExpirations:
    def test_happy_path_returns_from_first_provider(self):
        client = _make_client()
        p1 = _mock_provider()
        expected = [date(2024, 1, 19), date(2024, 2, 16)]
        p1.get_option_expirations.return_value = expected

        client._options_selector.select.return_value = [p1]

        result = client.get_option_expirations("AAPL")

        assert result == expected
        p1.get_option_expirations.assert_called_once_with("AAPL")

    def test_rate_limit_error_fails_over_to_next_provider(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()
        expected = [date(2024, 1, 19)]

        p1.get_option_expirations.side_effect = ProviderRateLimitError(
            "rate limited", provider="p1"
        )
        p2.get_option_expirations.return_value = expected

        client._options_selector.select.return_value = [p1, p2]

        result = client.get_option_expirations("AAPL")

        assert result == expected
        p1.get_option_expirations.assert_called_once_with("AAPL")
        p2.get_option_expirations.assert_called_once_with("AAPL")

    def test_ticker_not_found_reraises_immediately(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()

        p1.get_option_expirations.side_effect = TickerNotFoundError("not found", ticker="FAKE")

        client._options_selector.select.return_value = [p1, p2]

        with pytest.raises(TickerNotFoundError):
            client.get_option_expirations("FAKE")

        p2.get_option_expirations.assert_not_called()

    def test_not_implemented_skips_to_next_provider(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()
        expected = [date(2024, 3, 15)]

        p1.get_option_expirations.side_effect = NotImplementedError
        p2.get_option_expirations.return_value = expected

        client._options_selector.select.return_value = [p1, p2]

        result = client.get_option_expirations("AAPL")

        assert result == expected

    def test_all_providers_exhausted_raises_unavailable(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()

        exc = ProviderRateLimitError("rate limited", provider="p1")
        p1.get_option_expirations.side_effect = exc
        p2.get_option_expirations.side_effect = ProviderUnavailableError("unavailable")

        client._options_selector.select.return_value = [p1, p2]

        with pytest.raises(ProviderUnavailableError):
            client.get_option_expirations("AAPL")

    def test_auth_error_reraises_immediately(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()

        p1.get_option_expirations.side_effect = ProviderAuthError("auth failed", provider="p1")

        client._options_selector.select.return_value = [p1, p2]

        with pytest.raises(ProviderAuthError):
            client.get_option_expirations("AAPL")

        p2.get_option_expirations.assert_not_called()


# ---------------------------------------------------------------------------
# get_options_chain
# ---------------------------------------------------------------------------


class TestGetOptionsChain:
    def test_happy_path_returns_from_first_provider(self):
        client = _make_client()
        p1 = _mock_provider()
        exp = date(2024, 1, 19)
        expected = _sample_chain("AAPL", exp)
        p1.get_options_chain.return_value = expected

        client._options_selector.select.return_value = [p1]

        result = client.get_options_chain("AAPL", exp)

        assert result == expected
        p1.get_options_chain.assert_called_once_with("AAPL", exp)

    def test_rate_limit_error_fails_over_to_next_provider(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()
        exp = date(2024, 1, 19)
        expected = _sample_chain("AAPL", exp)

        p1.get_options_chain.side_effect = ProviderRateLimitError("rate limited", provider="p1")
        p2.get_options_chain.return_value = expected

        client._options_selector.select.return_value = [p1, p2]

        result = client.get_options_chain("AAPL", exp)

        assert result == expected
        p1.get_options_chain.assert_called_once_with("AAPL", exp)
        p2.get_options_chain.assert_called_once_with("AAPL", exp)

    def test_ticker_not_found_reraises_immediately(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()
        exp = date(2024, 1, 19)

        p1.get_options_chain.side_effect = TickerNotFoundError("not found", ticker="FAKE")

        client._options_selector.select.return_value = [p1, p2]

        with pytest.raises(TickerNotFoundError):
            client.get_options_chain("FAKE", exp)

        p2.get_options_chain.assert_not_called()

    def test_not_implemented_skips_to_next_provider(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()
        exp = date(2024, 1, 19)
        expected = _sample_chain("AAPL", exp)

        p1.get_options_chain.side_effect = NotImplementedError
        p2.get_options_chain.return_value = expected

        client._options_selector.select.return_value = [p1, p2]

        result = client.get_options_chain("AAPL", exp)

        assert result == expected

    def test_all_providers_exhausted_raises_unavailable(self):
        client = _make_client()
        p1 = _mock_provider()
        exp = date(2024, 1, 19)

        p1.get_options_chain.side_effect = ProviderUnavailableError("unavailable")

        client._options_selector.select.return_value = [p1]

        with pytest.raises(ProviderUnavailableError):
            client.get_options_chain("AAPL", exp)

    def test_auth_error_reraises_immediately(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()
        exp = date(2024, 1, 19)

        p1.get_options_chain.side_effect = ProviderAuthError("auth failed", provider="p1")

        client._options_selector.select.return_value = [p1, p2]

        with pytest.raises(ProviderAuthError):
            client.get_options_chain("AAPL", exp)

        p2.get_options_chain.assert_not_called()


# ---------------------------------------------------------------------------
# get_option_quote
# ---------------------------------------------------------------------------


class TestGetOptionQuote:
    def test_happy_path_returns_from_first_provider(self):
        client = _make_client()
        p1 = _mock_provider()
        symbol = "AAPL240119C00150000"
        expected = _sample_quote(symbol)
        p1.get_option_quote.return_value = expected

        client._options_selector.select.return_value = [p1]

        result = client.get_option_quote(symbol)

        assert result == expected
        p1.get_option_quote.assert_called_once_with(symbol)

    def test_rate_limit_error_fails_over_to_next_provider(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()
        symbol = "AAPL240119C00150000"
        expected = _sample_quote(symbol)

        p1.get_option_quote.side_effect = ProviderRateLimitError("rate limited", provider="p1")
        p2.get_option_quote.return_value = expected

        client._options_selector.select.return_value = [p1, p2]

        result = client.get_option_quote(symbol)

        assert result == expected
        p1.get_option_quote.assert_called_once_with(symbol)
        p2.get_option_quote.assert_called_once_with(symbol)

    def test_ticker_not_found_reraises_immediately(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()

        p1.get_option_quote.side_effect = TickerNotFoundError("not found", ticker="FAKEOPTION")

        client._options_selector.select.return_value = [p1, p2]

        with pytest.raises(TickerNotFoundError):
            client.get_option_quote("FAKEOPTION")

        p2.get_option_quote.assert_not_called()

    def test_not_implemented_skips_to_next_provider(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()
        symbol = "AAPL240119C00150000"
        expected = _sample_quote(symbol)

        p1.get_option_quote.side_effect = NotImplementedError
        p2.get_option_quote.return_value = expected

        client._options_selector.select.return_value = [p1, p2]

        result = client.get_option_quote(symbol)

        assert result == expected

    def test_all_providers_exhausted_raises_unavailable(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()

        p1.get_option_quote.side_effect = ProviderRateLimitError("rate limited", provider="p1")
        p2.get_option_quote.side_effect = ProviderUnavailableError("unavailable")

        client._options_selector.select.return_value = [p1, p2]

        with pytest.raises(ProviderUnavailableError):
            client.get_option_quote("AAPL240119C00150000")

    def test_auth_error_reraises_immediately(self):
        client = _make_client()
        p1 = _mock_provider()
        p2 = _mock_provider()

        p1.get_option_quote.side_effect = ProviderAuthError("auth failed", provider="p1")

        client._options_selector.select.return_value = [p1, p2]

        with pytest.raises(ProviderAuthError):
            client.get_option_quote("AAPL240119C00150000")

        p2.get_option_quote.assert_not_called()
