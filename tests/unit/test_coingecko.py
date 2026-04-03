"""Unit tests for CoingeckoProvider and CoingeckoNormalizer."""

from __future__ import annotations

import pytest

from stockfeed.providers.coingecko.provider import CoingeckoProvider


class TestCoingeckoProvider:
    """Coingecko is a stub — all methods raise NotImplementedError."""

    def setup_method(self) -> None:
        self.p = CoingeckoProvider(api_key="testkey")

    def test_get_ohlcv_raises(self) -> None:
        from datetime import datetime, timezone

        from stockfeed.models.interval import Interval
        with pytest.raises(NotImplementedError):
            self.p.get_ohlcv("BTC", Interval.ONE_DAY,
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 31, tzinfo=timezone.utc))

    def test_get_quote_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            self.p.get_quote("BTC")

    def test_get_ticker_info_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            self.p.get_ticker_info("BTC")

    def test_health_check_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            self.p.health_check()

    def test_async_methods_raise(self) -> None:
        import asyncio
        from datetime import datetime, timezone

        from stockfeed.models.interval import Interval

        async def _run() -> None:
            with pytest.raises(NotImplementedError):
                await self.p.async_get_ohlcv("BTC", Interval.ONE_DAY,
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 1, 31, tzinfo=timezone.utc))
            with pytest.raises(NotImplementedError):
                await self.p.async_get_quote("BTC")
            with pytest.raises(NotImplementedError):
                await self.p.async_get_ticker_info("BTC")
            with pytest.raises(NotImplementedError):
                await self.p.async_health_check()

        asyncio.run(_run())


class TestCoingeckoNormalizer:
    def setup_method(self) -> None:
        from stockfeed.providers.coingecko.normalizer import CoingeckoNormalizer
        self.n = CoingeckoNormalizer()

    def test_normalize_ohlcv_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            self.n.normalize_ohlcv("any")

    def test_normalize_quote_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            self.n.normalize_quote("any")

    def test_normalize_ticker_info_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            self.n.normalize_ticker_info("any")
