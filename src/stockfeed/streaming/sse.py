"""Streaming quote generator — polls a provider and yields Quote objects."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from stockfeed.exceptions import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    TickerNotFoundError,
)
from stockfeed.models.quote import Quote

if TYPE_CHECKING:
    from stockfeed.async_client import AsyncStockFeedClient


async def stream_quote(
    ticker: str,
    client: AsyncStockFeedClient,
    *,
    interval: float = 5.0,
    provider: str | None = None,
    max_errors: int = 5,
) -> AsyncGenerator[Quote, None]:
    """Continuously poll *ticker* and yield the latest :class:`~stockfeed.models.quote.Quote`.

    Polls ``client.get_quote()`` every *interval* seconds and yields each
    result. The generator runs indefinitely until the caller breaks out of
    the loop or calls ``aclose()``.

    Transient errors (:class:`~stockfeed.exceptions.ProviderRateLimitError`,
    :class:`~stockfeed.exceptions.ProviderUnavailableError`) are swallowed and
    retried; after *max_errors* consecutive failures the generator raises the
    last exception. Fatal errors
    (:class:`~stockfeed.exceptions.ProviderAuthError`,
    :class:`~stockfeed.exceptions.TickerNotFoundError`) propagate immediately.

    Parameters
    ----------
    ticker : str
        Uppercase ticker symbol to stream.
    client : AsyncStockFeedClient
        Configured async client (handles provider selection and failover).
    interval : float
        Seconds between polls. Defaults to ``5.0``.
    provider : str | None
        Pin a specific provider. ``None`` means auto-select.
    max_errors : int
        Maximum consecutive transient errors before aborting. Defaults to ``5``.

    Yields
    ------
    Quote
        The latest quote snapshot.

    Raises
    ------
    ProviderAuthError
        Immediately on bad credentials.
    TickerNotFoundError
        Immediately if the ticker doesn't exist.
    ProviderUnavailableError
        After *max_errors* consecutive failures.
    """
    consecutive_errors = 0

    while True:
        try:
            quote = await client.get_quote(ticker, provider=provider)
            consecutive_errors = 0
            yield quote
        except (ProviderAuthError, TickerNotFoundError):
            raise
        except (ProviderRateLimitError, ProviderUnavailableError) as exc:
            consecutive_errors += 1
            if consecutive_errors >= max_errors:
                raise
            retry_after = getattr(exc, "retry_after", None) or interval
            await asyncio.sleep(float(retry_after))
            continue

        await asyncio.sleep(interval)
