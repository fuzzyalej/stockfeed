"""Unit tests for stockfeed.streaming.sse — stream_quote async generator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stockfeed.exceptions import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    TickerNotFoundError,
)
from stockfeed.streaming.sse import stream_quote


def _make_quote(ticker: str = "AAPL") -> MagicMock:
    q = MagicMock()
    q.ticker = ticker
    return q


def _make_client(quotes: list) -> MagicMock:
    """Return a mock AsyncStockFeedClient whose get_quote yields from quotes."""
    client = MagicMock()
    client.get_quote = AsyncMock(side_effect=quotes)
    return client


async def _collect(gen, n: int) -> list:
    """Collect up to n items from an async generator."""
    items = []
    async for item in gen:
        items.append(item)
        if len(items) >= n:
            break
    return items


class TestStreamQuote:
    async def test_yields_quotes(self) -> None:
        q1, q2 = _make_quote(), _make_quote()
        client = _make_client([q1, q2, q2])

        with patch("stockfeed.streaming.sse.asyncio.sleep", new_callable=AsyncMock):
            results = await _collect(stream_quote("AAPL", client, interval=0.0), 2)

        assert results == [q1, q2]

    async def test_calls_get_quote_with_provider(self) -> None:
        q = _make_quote()
        client = _make_client([q, q])

        with patch("stockfeed.streaming.sse.asyncio.sleep", new_callable=AsyncMock):
            await _collect(stream_quote("AAPL", client, interval=0.0, provider="tiingo"), 1)

        client.get_quote.assert_called_with("AAPL", provider="tiingo")

    async def test_auth_error_propagates_immediately(self) -> None:
        client = _make_client([ProviderAuthError("bad key", provider="p1")])

        with (
            pytest.raises(ProviderAuthError),
            patch("stockfeed.streaming.sse.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _collect(stream_quote("AAPL", client, interval=0.0), 1)

    async def test_ticker_not_found_propagates_immediately(self) -> None:
        client = _make_client([TickerNotFoundError("nope", ticker="FAKE")])

        with (
            pytest.raises(TickerNotFoundError),
            patch("stockfeed.streaming.sse.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _collect(stream_quote("AAPL", client, interval=0.0), 1)

    async def test_transient_error_retries(self) -> None:
        q = _make_quote()
        client = _make_client(
            [
                ProviderUnavailableError("down", provider="p1"),
                q,
            ]
        )

        with patch("stockfeed.streaming.sse.asyncio.sleep", new_callable=AsyncMock):
            results = await _collect(stream_quote("AAPL", client, interval=0.0), 1)

        assert results == [q]

    async def test_rate_limit_error_retries_with_retry_after(self) -> None:
        q = _make_quote()
        exc = ProviderRateLimitError("limited", provider="p1", retry_after=0.1)
        client = _make_client([exc, q])

        sleep_calls: list[float] = []

        async def _fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with patch("stockfeed.streaming.sse.asyncio.sleep", side_effect=_fake_sleep):
            results = await _collect(stream_quote("AAPL", client, interval=1.0), 1)

        assert results == [q]
        # Should have slept with retry_after value, not interval
        assert sleep_calls[0] == pytest.approx(0.1)

    async def test_max_errors_raises_after_threshold(self) -> None:
        errors = [ProviderUnavailableError("down", provider="p1")] * 5
        client = _make_client(errors)

        with (
            pytest.raises(ProviderUnavailableError),
            patch("stockfeed.streaming.sse.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _collect(stream_quote("AAPL", client, interval=0.0, max_errors=5), 1)

    async def test_sleep_called_with_interval(self) -> None:
        q1, q2 = _make_quote(), _make_quote()
        client = _make_client([q1, q2])
        sleep_calls: list[float] = []

        async def _fake_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with patch("stockfeed.streaming.sse.asyncio.sleep", side_effect=_fake_sleep):
            await _collect(stream_quote("AAPL", client, interval=2.5), 2)

        # Should have slept after first yield
        assert 2.5 in sleep_calls
