"""HealthChecker — runs provider health checks and persists results."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from stockfeed.cache.connection import get_connection
from stockfeed.cache.schema import run_migrations
from stockfeed.models.health import HealthStatus

if TYPE_CHECKING:
    from stockfeed.providers.base import AbstractProvider


class HealthChecker:
    """Run health checks against providers and log results to DuckDB.

    Parameters
    ----------
    db_path : str
        Path to the DuckDB cache database.
    """

    def __init__(self, db_path: str = "~/.stockfeed/cache.db") -> None:
        self._db_path = db_path
        conn = get_connection(db_path)
        run_migrations(conn)

    def check(self, provider: AbstractProvider) -> HealthStatus:
        """Run the provider's health check and persist the result.

        Parameters
        ----------
        provider : AbstractProvider
            The provider to probe.

        Returns
        -------
        HealthStatus
            Result of the health check including latency measurement.
        """
        start = time.monotonic()
        try:
            status = provider.health_check()
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            status = HealthStatus(
                provider=provider.name,
                healthy=False,
                latency_ms=latency_ms,
                error=str(exc),
                checked_at=datetime.now(timezone.utc),
                rate_limit_remaining=None,
            )

        self._persist(status)
        return status

    async def async_check(self, provider: AbstractProvider) -> HealthStatus:
        """Async variant of :meth:`check`.

        Parameters
        ----------
        provider : AbstractProvider
            The provider to probe.
        """
        start = time.monotonic()
        try:
            status = await provider.async_health_check()
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            status = HealthStatus(
                provider=provider.name,
                healthy=False,
                latency_ms=latency_ms,
                error=str(exc),
                checked_at=datetime.now(timezone.utc),
                rate_limit_remaining=None,
            )

        self._persist(status)
        return status

    def _persist(self, status: HealthStatus) -> None:
        conn = get_connection(self._db_path)
        conn.execute(
            """
            INSERT INTO provider_health_log
                (provider, healthy, latency_ms, error, checked_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                status.provider,
                status.healthy,
                status.latency_ms,
                status.error,
                status.checked_at,
            ],
        )

    def last_status(self, provider_name: str) -> HealthStatus | None:
        """Return the most recent recorded health status for *provider_name*.

        Parameters
        ----------
        provider_name : str
            Provider identifier.

        Returns
        -------
        HealthStatus or None
            ``None`` if no health check has been recorded yet.
        """
        conn = get_connection(self._db_path)
        row = conn.execute(
            """
            SELECT provider, healthy, latency_ms, error, checked_at
            FROM provider_health_log
            WHERE provider = ?
            ORDER BY checked_at DESC
            LIMIT 1
            """,
            [provider_name],
        ).fetchone()
        if row is None:
            return None
        provider, healthy, latency_ms, error, checked_at = row
        return HealthStatus(
            provider=provider,
            healthy=healthy,
            latency_ms=latency_ms,
            error=error,
            checked_at=checked_at,
            rate_limit_remaining=None,
        )
