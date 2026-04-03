"""Unit tests for HealthChecker."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

from stockfeed.models.health import HealthStatus
from stockfeed.providers.health import HealthChecker


def _status(provider: str = "yfinance", healthy: bool = True) -> HealthStatus:
    return HealthStatus(
        provider=provider,
        healthy=healthy,
        latency_ms=12.0,
        error=None,
        checked_at=datetime.now(timezone.utc),
        rate_limit_remaining=None,
    )


class TestHealthCheckerSync:
    def test_check_returns_status_on_success(self, tmp_db_path: str) -> None:
        checker = HealthChecker(db_path=tmp_db_path)
        provider = MagicMock()
        provider.name = "yfinance"
        provider.health_check.return_value = _status()

        result = checker.check(provider)
        assert isinstance(result, HealthStatus)
        assert result.healthy is True

    def test_check_returns_unhealthy_status_on_exception(self, tmp_db_path: str) -> None:
        checker = HealthChecker(db_path=tmp_db_path)
        provider = MagicMock()
        provider.name = "tiingo"
        provider.health_check.side_effect = RuntimeError("connection refused")

        result = checker.check(provider)
        assert result.healthy is False
        assert result.error is not None
        assert "connection refused" in result.error

    def test_check_persists_result(self, tmp_db_path: str) -> None:
        checker = HealthChecker(db_path=tmp_db_path)
        provider = MagicMock()
        provider.name = "finnhub"
        provider.health_check.return_value = _status("finnhub")

        checker.check(provider)
        last = checker.last_status("finnhub")

        assert last is not None
        assert last.provider == "finnhub"

    def test_last_status_returns_none_if_never_checked(self, tmp_db_path: str) -> None:
        checker = HealthChecker(db_path=tmp_db_path)
        assert checker.last_status("never_checked") is None

    def test_last_status_returns_most_recent(self, tmp_db_path: str) -> None:
        checker = HealthChecker(db_path=tmp_db_path)

        provider = MagicMock()
        provider.name = "tiingo"
        provider.health_check.return_value = _status("tiingo", healthy=False)
        checker.check(provider)

        provider.health_check.return_value = _status("tiingo", healthy=True)
        checker.check(provider)

        last = checker.last_status("tiingo")
        assert last is not None
        assert last.healthy is True


class TestHealthCheckerAsync:
    def test_async_check_returns_status(self, tmp_db_path: str) -> None:
        checker = HealthChecker(db_path=tmp_db_path)
        status = _status()

        async def _async_health() -> HealthStatus:
            return status

        provider = MagicMock()
        provider.name = "yfinance"
        provider.async_health_check = _async_health

        result = asyncio.run(checker.async_check(provider))
        assert result.healthy is True

    def test_async_check_catches_exception(self, tmp_db_path: str) -> None:
        checker = HealthChecker(db_path=tmp_db_path)

        async def _fail() -> HealthStatus:
            raise ConnectionError("timeout")

        provider = MagicMock()
        provider.name = "tiingo"
        provider.async_health_check = _fail

        result = asyncio.run(checker.async_check(provider))
        assert result.healthy is False
        assert "timeout" in (result.error or "")

    def test_async_check_persists_result(self, tmp_db_path: str) -> None:
        checker = HealthChecker(db_path=tmp_db_path)
        status = _status("alpaca")

        async def _ok() -> HealthStatus:
            return status

        provider = MagicMock()
        provider.name = "alpaca"
        provider.async_health_check = _ok

        asyncio.run(checker.async_check(provider))
        last = checker.last_status("alpaca")
        assert last is not None
