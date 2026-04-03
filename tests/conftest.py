"""Shared fixtures for the test suite."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from stockfeed.config import StockFeedSettings
from stockfeed.models.health import HealthStatus
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo

# ---------------------------------------------------------------------------
# Database / settings
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """Return a temporary DuckDB file path inside pytest's tmp_path."""
    return str(tmp_path / "test_cache.db")


@pytest.fixture
def settings(tmp_db_path: str) -> StockFeedSettings:
    """Return a StockFeedSettings instance pointing to a temp DB, no API keys."""
    return StockFeedSettings(
        cache_path=tmp_db_path,
        cache_enabled=True,
        dev_mode=False,
        log_level="WARNING",
    )


@pytest.fixture
def dev_settings(tmp_db_path: str) -> StockFeedSettings:
    """Like `settings` but with dev_mode=True."""
    return StockFeedSettings(
        cache_path=tmp_db_path,
        cache_enabled=True,
        dev_mode=True,
        log_level="WARNING",
    )


# ---------------------------------------------------------------------------
# Model factories — plain functions so they can be called outside fixtures
# ---------------------------------------------------------------------------


def make_bar(
    ticker: str = "AAPL",
    days_offset: int = 0,
    interval: Interval = Interval.ONE_DAY,
    provider: str = "test",
) -> OHLCVBar:
    """Return a minimal valid OHLCVBar for testing."""
    ts = datetime(2024, 1, 1 + days_offset, tzinfo=timezone.utc)
    return OHLCVBar(
        ticker=ticker,
        timestamp=ts,
        interval=interval,
        open=Decimal("185.50"),
        high=Decimal("188.44"),
        low=Decimal("183.00"),
        close_raw=Decimal("187.20"),
        close_adj=Decimal("187.20"),
        volume=1_000_000,
        vwap=None,
        trade_count=None,
        provider=provider,
    )


def make_quote(
    ticker: str = "AAPL",
    provider: str = "test",
) -> Quote:
    """Return a minimal valid Quote for testing."""
    return Quote(
        ticker=ticker,
        timestamp=datetime(2024, 1, 2, 15, 30, tzinfo=timezone.utc),
        bid=Decimal("186.90"),
        ask=Decimal("187.10"),
        bid_size=100,
        ask_size=200,
        last=Decimal("187.00"),
        last_size=50,
        volume=10_000_000,
        open=Decimal("185.00"),
        high=Decimal("188.00"),
        low=Decimal("184.00"),
        close=Decimal("186.50"),
        change=Decimal("0.50"),
        change_pct=Decimal("0.27"),
        provider=provider,
    )


def make_ticker_info(
    ticker: str = "AAPL",
    provider: str = "test",
) -> TickerInfo:
    """Return a minimal valid TickerInfo for testing."""
    return TickerInfo(
        ticker=ticker,
        name="Apple Inc.",
        exchange="NASDAQ",
        currency="USD",
        country="US",
        sector="Technology",
        industry="Consumer Electronics",
        market_cap=3_000_000_000_000,
        provider=provider,
    )


def make_health(
    provider: str = "test",
    healthy: bool = True,
) -> HealthStatus:
    """Return a minimal valid HealthStatus for testing."""
    return HealthStatus(
        provider=provider,
        healthy=healthy,
        latency_ms=12.5,
        error=None,
        checked_at=datetime(2024, 1, 2, 15, 0, tzinfo=timezone.utc),
        rate_limit_remaining=None,
    )


# ---------------------------------------------------------------------------
# Pytest fixtures wrapping the factories
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_bar() -> OHLCVBar:
    """A single OHLCVBar for AAPL 2024-01-01."""
    return make_bar()


@pytest.fixture
def sample_bars() -> list[OHLCVBar]:
    """Five consecutive OHLCVBars for AAPL starting 2024-01-01."""
    return [make_bar(days_offset=i) for i in range(5)]


@pytest.fixture
def sample_quote() -> Quote:
    """A Quote for AAPL."""
    return make_quote()


@pytest.fixture
def sample_ticker_info() -> TickerInfo:
    """A TickerInfo for AAPL."""
    return make_ticker_info()


@pytest.fixture
def sample_health() -> HealthStatus:
    """A healthy HealthStatus."""
    return make_health()


# ---------------------------------------------------------------------------
# Fixtures path helper
# ---------------------------------------------------------------------------


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the root of the tests/fixtures directory."""
    return Path(__file__).parent / "fixtures"
