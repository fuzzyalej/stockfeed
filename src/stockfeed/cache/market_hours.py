"""MarketHoursChecker — decide whether to use cache based on market hours."""

from __future__ import annotations

from datetime import datetime, timezone

import exchange_calendars as xcals

from stockfeed.models.interval import Interval

# Intervals considered "intraday" (sub-daily)
_INTRADAY_INTERVALS = {
    Interval.ONE_MINUTE,
    Interval.FIVE_MINUTES,
    Interval.FIFTEEN_MINUTES,
    Interval.THIRTY_MINUTES,
    Interval.ONE_HOUR,
    Interval.FOUR_HOURS,
}

# Mapping from common exchange codes to exchange_calendars keys
_EXCHANGE_MAP: dict[str, str] = {
    "NMS": "XNAS",   # NASDAQ
    "NGM": "XNAS",
    "NYQ": "XNYS",   # NYSE
    "PCX": "XNYS",   # NYSE Arca
    "ASE": "XNYS",   # NYSE American
    "XNYS": "XNYS",
    "XNAS": "XNAS",
    "LSE": "XLON",
    "XLON": "XLON",
}

_DEFAULT_CALENDAR = "XNYS"  # NYSE


class MarketHoursChecker:
    """Check whether a market is open and whether the cache should be used.

    Parameters
    ----------
    default_exchange : str
        exchange_calendars key used when the ticker's exchange is unknown.
        Defaults to ``"XNYS"`` (NYSE).
    """

    def __init__(self, default_exchange: str = _DEFAULT_CALENDAR) -> None:
        self._default = default_exchange
        self._calendars: dict[str, xcals.ExchangeCalendar] = {}

    def _get_calendar(self, exchange: str) -> xcals.ExchangeCalendar:
        key = _EXCHANGE_MAP.get(exchange, exchange)
        if key not in self._calendars:
            try:
                self._calendars[key] = xcals.get_calendar(key)
            except Exception:
                # Unknown exchange — fall back to default
                if self._default not in self._calendars:
                    self._calendars[self._default] = xcals.get_calendar(self._default)
                return self._calendars[self._default]
        return self._calendars[key]

    def is_market_open(self, exchange: str, dt: datetime | None = None) -> bool:
        """Return ``True`` if *exchange* is currently open at *dt*.

        Parameters
        ----------
        exchange : str
            Exchange identifier (e.g. ``"XNYS"``, ``"NMS"``, ``"XNAS"``).
        dt : datetime | None
            Point in time to check. Defaults to ``datetime.now(UTC)``.

        Returns
        -------
        bool
        """
        if dt is None:
            dt = datetime.now(timezone.utc)
        cal = self._get_calendar(exchange)
        try:
            return bool(cal.is_open_at_time(dt))
        except Exception:
            return False

    def should_use_cache(
        self,
        interval: Interval,
        exchange: str = _DEFAULT_CALENDAR,
        dt: datetime | None = None,
    ) -> bool:
        """Return ``True`` if the cache should be used for this request.

        Cache bypass rules:
        - Intraday intervals during open market hours → ``False`` (always re-fetch)
        - Everything else → ``True``

        Parameters
        ----------
        interval : Interval
            Bar width of the request.
        exchange : str
            Exchange to check market hours against.
        dt : datetime | None
            Point in time. Defaults to now (UTC).

        Returns
        -------
        bool
        """
        if interval not in _INTRADAY_INTERVALS:
            return True
        return not self.is_market_open(exchange, dt)
