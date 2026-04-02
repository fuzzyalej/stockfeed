"""Per-provider rate limit tracking persisted in DuckDB."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import duckdb

from stockfeed.cache.connection import get_connection
from stockfeed.cache.schema import run_migrations


class RateLimiter:
    """Track and enforce per-provider rate limits, persisted in DuckDB.

    State survives process restarts so a crashed-and-restarted process
    does not immediately re-hammer a provider that was already limited.

    Parameters
    ----------
    db_path : str
        Path to the DuckDB cache database.
    """

    def __init__(self, db_path: str = "~/.stockfeed/cache.db") -> None:
        self._db_path = db_path
        conn = get_connection(db_path)
        run_migrations(conn)

    @property
    def _conn(self) -> duckdb.DuckDBPyConnection:
        return get_connection(self._db_path)

    def is_available(self, provider: str) -> bool:
        """Return ``True`` if the provider has not exceeded its rate limit.

        A provider with no recorded state is considered available.

        Parameters
        ----------
        provider : str
            Provider name (e.g. ``"tiingo"``).
        """
        row = self._conn.execute(
            "SELECT requests_made, window_start, window_seconds, limit_per_window "
            "FROM rate_limit_state WHERE provider = ?",
            [provider],
        ).fetchone()
        if row is None:
            return True
        requests_made, window_start, window_seconds, limit_per_window = row
        if limit_per_window is None or window_seconds is None:
            return True
        # Check if the window has expired
        if window_start is not None:
            now = datetime.now(timezone.utc)
            elapsed = (now - window_start.replace(tzinfo=timezone.utc)).total_seconds()
            if elapsed >= window_seconds:
                return True  # Window expired
        return int(requests_made) < int(limit_per_window)

    def record_request(self, provider: str) -> None:
        """Increment the request counter for *provider*.

        Parameters
        ----------
        provider : str
            Provider name.
        """
        now = datetime.now(timezone.utc)
        self._conn.execute(
            """
            INSERT INTO rate_limit_state (provider, requests_made, window_start, updated_at)
            VALUES (?, 1, ?, ?)
            ON CONFLICT (provider) DO UPDATE SET
                requests_made = rate_limit_state.requests_made + 1,
                updated_at = excluded.updated_at
            """,
            [provider, now, now],
        )

    def update_from_headers(self, provider: str, headers: dict[str, Any]) -> None:
        """Update rate limit state from HTTP response headers.

        Looks for common rate-limit headers:
        - ``X-RateLimit-Remaining``
        - ``X-RateLimit-Limit``
        - ``X-RateLimit-Reset`` (seconds until reset)
        - ``Retry-After``

        Parameters
        ----------
        provider : str
            Provider name.
        headers : dict
            HTTP response headers (case-insensitive lookup attempted).
        """
        # Normalise header keys to lower-case for lookup
        h = {k.lower(): v for k, v in headers.items()}
        now = datetime.now(timezone.utc)

        remaining = h.get("x-ratelimit-remaining")
        limit = h.get("x-ratelimit-limit")
        reset = h.get("x-ratelimit-reset") or h.get("retry-after")

        window_seconds: int | None = int(reset) if reset is not None else None
        limit_per_window: int | None = int(limit) if limit is not None else None
        requests_made: int | None = (
            (int(limit) - int(remaining)) if limit is not None and remaining is not None else None
        )

        self._conn.execute(
            """
            INSERT INTO rate_limit_state
                (provider, requests_made, window_start, window_seconds, limit_per_window, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (provider) DO UPDATE SET
                requests_made    = COALESCE(excluded.requests_made, rate_limit_state.requests_made),
                window_seconds   = COALESCE(excluded.window_seconds, rate_limit_state.window_seconds),
                limit_per_window = COALESCE(excluded.limit_per_window, rate_limit_state.limit_per_window),
                updated_at       = excluded.updated_at
            """,
            [provider, requests_made, now, window_seconds, limit_per_window, now],
        )

    def reset_window(self, provider: str) -> None:
        """Reset the request counter and window start for *provider*.

        Parameters
        ----------
        provider : str
            Provider name.
        """
        now = datetime.now(timezone.utc)
        self._conn.execute(
            """
            INSERT INTO rate_limit_state (provider, requests_made, window_start, updated_at)
            VALUES (?, 0, ?, ?)
            ON CONFLICT (provider) DO UPDATE SET
                requests_made = 0,
                window_start  = excluded.window_start,
                updated_at    = excluded.updated_at
            """,
            [provider, now, now],
        )
