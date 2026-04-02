"""Shared fixtures for the test suite."""

from pathlib import Path

import pytest

from stockfeed.config import StockFeedSettings


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
