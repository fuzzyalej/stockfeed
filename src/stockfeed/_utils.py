"""Internal helpers shared across the public client API."""

from __future__ import annotations

from datetime import datetime, timezone

from stockfeed.models.interval import Interval


def parse_dt(value: str | datetime) -> datetime:
    """Coerce a date string or datetime to a UTC-aware datetime.

    Parameters
    ----------
    value : str | datetime
        A ``datetime`` (returned as-is, naive assumed UTC) or an ISO date
        string ``"YYYY-MM-DD"`` / ``"YYYY-MM-DDTHH:MM:SS"`` (parsed as UTC
        midnight / UTC second).

    Returns
    -------
    datetime
        Timezone-aware datetime in UTC.

    Raises
    ------
    ValueError
        If *value* is a string that cannot be parsed.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    # String path — try ISO date first, then ISO datetime
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date {value!r}. Use 'YYYY-MM-DD' or a datetime object.")


def parse_interval(value: str | Interval) -> Interval:
    """Coerce a string or Interval to an Interval enum member.

    Parameters
    ----------
    value : str | Interval
        ``"1d"``, ``"1h"``, etc., or an :class:`~stockfeed.models.interval.Interval`
        directly.

    Returns
    -------
    Interval

    Raises
    ------
    ValueError
        If *value* is a string that doesn't match any Interval.
    """
    if isinstance(value, Interval):
        return value
    try:
        return Interval(value)
    except ValueError:
        valid = ", ".join(i.value for i in Interval)
        raise ValueError(f"Unknown interval {value!r}. Valid values: {valid}") from None
