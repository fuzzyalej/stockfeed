"""Unit tests for ProviderRegistry."""

from __future__ import annotations

import pytest

from stockfeed.providers.registry import ProviderRegistry, get_default_registry


class TestProviderRegistry:
    def test_register_and_get(self) -> None:
        reg = ProviderRegistry()
        from stockfeed.providers.yfinance.provider import YFinanceProvider
        reg.register(YFinanceProvider)
        assert reg.get("yfinance") is YFinanceProvider

    def test_get_unknown_raises_key_error(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(KeyError, match="Unknown provider"):
            reg.get("nonexistent")

    def test_get_includes_available_names_in_error(self) -> None:
        reg = ProviderRegistry()
        from stockfeed.providers.yfinance.provider import YFinanceProvider
        reg.register(YFinanceProvider)
        with pytest.raises(KeyError, match="yfinance"):
            reg.get("bogus")

    def test_get_error_on_empty_registry(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(KeyError, match="none registered"):
            reg.get("anything")

    def test_all_returns_snapshot(self) -> None:
        reg = ProviderRegistry()
        from stockfeed.providers.yfinance.provider import YFinanceProvider
        reg.register(YFinanceProvider)
        snapshot = reg.all()
        assert "yfinance" in snapshot
        # Mutating the snapshot doesn't affect registry
        del snapshot["yfinance"]
        assert "yfinance" in reg.all()

    def test_discover_entry_points_does_not_raise(self) -> None:
        reg = ProviderRegistry()
        # No stockfeed.providers entry points registered in test env — should be no-op
        reg.discover_entry_points()

    def test_get_default_registry_returns_singleton(self) -> None:
        r1 = get_default_registry()
        r2 = get_default_registry()
        assert r1 is r2
