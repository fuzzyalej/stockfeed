"""Dev-mode bar simulator — replays historical OHLCV bars as an async stream."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import TYPE_CHECKING

from stockfeed._utils import parse_dt, parse_interval
from stockfeed.exceptions import DevModeError
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar

if TYPE_CHECKING:
    from stockfeed.async_client import AsyncStockFeedClient

# Seconds per interval value — used to compute sleep duration
_INTERVAL_SECONDS: dict[Interval, float] = {
    Interval.ONE_MINUTE: 60.0,
    Interval.FIVE_MINUTES: 300.0,
    Interval.FIFTEEN_MINUTES: 900.0,
    Interval.THIRTY_MINUTES: 1800.0,
    Interval.ONE_HOUR: 3600.0,
    Interval.FOUR_HOURS: 14400.0,
    Interval.ONE_DAY: 86400.0,
    Interval.ONE_WEEK: 604800.0,
    Interval.ONE_MONTH: 2592000.0,
}


async def simulate(
    ticker: str,
    start: str | datetime,
    end: str | datetime,
    interval: str | Interval,
    *,
    speed: float = 1.0,
    client: AsyncStockFeedClient,
) -> AsyncGenerator[OHLCVBar, None]:
    """Replay historical bars for *ticker* as an async stream.

    Fetches bars from the cache (or provider on a miss) and yields them in
    ascending timestamp order, sleeping between bars to simulate real-time
    playback.

    Parameters
    ----------
    ticker : str
        Uppercase ticker symbol.
    start : str | datetime
        Inclusive start. ``"YYYY-MM-DD"`` strings are accepted.
    end : str | datetime
        Exclusive end.
    interval : str | Interval
        Bar width — ``"1d"``, ``"1h"``, etc.
    speed : float
        Playback multiplier.  ``1.0`` replays at real-time pace (e.g. one
        daily bar per 86 400 s). ``0`` skips all sleeps for instant replay.
        ``10.0`` plays back 10× faster than real time. Defaults to ``1.0``.
    client : AsyncStockFeedClient
        Configured async client used to fetch missing bars.

    Yields
    ------
    OHLCVBar
        Bars in ascending timestamp order.

    Raises
    ------
    DevModeError
        If ``client.settings.dev_mode`` is ``False``.
    """
    if not client.settings.dev_mode:
        raise DevModeError(
            "simulate() requires dev_mode=True. "
            "Pass dev_mode=True to AsyncStockFeedClient or set "
            "STOCKFEED_DEV_MODE=true in your environment.",
            suggestion="AsyncStockFeedClient(dev_mode=True)",
        )

    interval = parse_interval(interval)
    start_dt = parse_dt(start)
    end_dt = parse_dt(end)

    bars = await client.get_ohlcv(ticker, interval, start_dt, end_dt)
    bars = sorted(bars, key=lambda b: b.timestamp)

    sleep_per_bar = _INTERVAL_SECONDS.get(interval, 0.0)
    if speed > 0:
        sleep_per_bar = sleep_per_bar / speed

    for bar in bars:
        yield bar
        if speed != 0 and sleep_per_bar > 0:
            await asyncio.sleep(sleep_per_bar)
