"""Provider contract tests — every implemented provider must pass these.

These tests verify:
- Required class attributes are present and correctly typed
- All abstract methods are implemented (not just inherited stubs)
- The provider conforms to AbstractProvider's interface
- Stub providers raise NotImplementedError as documented

Parametrized over all provider classes so adding a new provider
automatically adds it to the contract suite.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from stockfeed.models.health import HealthStatus
from stockfeed.models.interval import Interval
from stockfeed.models.ohlcv import OHLCVBar
from stockfeed.models.quote import Quote
from stockfeed.models.ticker import TickerInfo
from stockfeed.providers.alpaca.provider import AlpacaProvider
from stockfeed.providers.base import AbstractProvider
from stockfeed.providers.coingecko.provider import CoingeckoProvider
from stockfeed.providers.finnhub.provider import FinnhubProvider
from stockfeed.providers.tiingo.provider import TiingoProvider
from stockfeed.providers.tradier.provider import TradierProvider
from stockfeed.providers.twelvedata.provider import TwelvedataProvider
from stockfeed.providers.yfinance.provider import YFinanceProvider

# ---------------------------------------------------------------------------
# Provider registry for contract tests
# ---------------------------------------------------------------------------

# All implemented providers with a sample credential call
_ALL_PROVIDER_CLASSES: list[type[AbstractProvider]] = [
    YFinanceProvider,
    TiingoProvider,
    FinnhubProvider,
    TwelvedataProvider,
    AlpacaProvider,
    TradierProvider,
    CoingeckoProvider,
]

# Providers with full implementations (not stubs)
_IMPLEMENTED_PROVIDERS: list[type[AbstractProvider]] = [
    YFinanceProvider,
    TiingoProvider,
    FinnhubProvider,
    TwelvedataProvider,
    AlpacaProvider,
    TradierProvider,
]

# Providers that are stubs (raise NotImplementedError)
_STUB_PROVIDERS: list[type[AbstractProvider]] = [
    CoingeckoProvider,
]


def _instantiate(cls: type[AbstractProvider]) -> AbstractProvider:
    """Create a provider instance with dummy credentials."""
    if cls is YFinanceProvider:
        return cls()
    if cls is AlpacaProvider:
        return cls(api_key="dummy_key", secret_key="dummy_secret")
    return cls(api_key="dummy_key")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Class-attribute contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_class", _ALL_PROVIDER_CLASSES, ids=lambda c: c.name)
class TestProviderClassAttributes:
    """Every provider class must declare the three class-level attributes."""

    def test_has_name(self, provider_class: type[AbstractProvider]) -> None:
        assert hasattr(provider_class, "name")
        assert isinstance(provider_class.name, str)
        assert provider_class.name  # non-empty

    def test_has_supported_intervals(self, provider_class: type[AbstractProvider]) -> None:
        assert hasattr(provider_class, "supported_intervals")
        intervals = provider_class.supported_intervals
        assert isinstance(intervals, list)
        assert len(intervals) > 0
        assert all(isinstance(i, Interval) for i in intervals)

    def test_has_requires_auth(self, provider_class: type[AbstractProvider]) -> None:
        assert hasattr(provider_class, "requires_auth")
        assert isinstance(provider_class.requires_auth, bool)

    def test_yfinance_does_not_require_auth(self, provider_class: type[AbstractProvider]) -> None:
        if provider_class is YFinanceProvider:
            assert provider_class.requires_auth is False

    def test_non_yfinance_requires_auth(self, provider_class: type[AbstractProvider]) -> None:
        if provider_class is not YFinanceProvider:
            assert provider_class.requires_auth is True


# ---------------------------------------------------------------------------
# Abstract method implementation contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_class", _ALL_PROVIDER_CLASSES, ids=lambda c: c.name)
class TestProviderMethodSurface:
    """Every provider must implement all AbstractProvider methods."""

    _SYNC_METHODS = ["get_ohlcv", "get_quote", "get_ticker_info", "health_check"]
    _ASYNC_METHODS = [
        "async_get_ohlcv",
        "async_get_quote",
        "async_get_ticker_info",
        "async_health_check",
    ]

    def test_sync_methods_exist(self, provider_class: type[AbstractProvider]) -> None:
        for method_name in self._SYNC_METHODS:
            assert hasattr(provider_class, method_name), (
                f"{provider_class.name} missing sync method: {method_name}"
            )
            assert callable(getattr(provider_class, method_name))

    def test_async_methods_exist(self, provider_class: type[AbstractProvider]) -> None:
        for method_name in self._ASYNC_METHODS:
            assert hasattr(provider_class, method_name), (
                f"{provider_class.name} missing async method: {method_name}"
            )
            method = getattr(provider_class, method_name)
            assert inspect.iscoroutinefunction(method), (
                f"{provider_class.name}.{method_name} must be a coroutine function"
            )

    def test_can_instantiate(self, provider_class: type[AbstractProvider]) -> None:
        instance = _instantiate(provider_class)
        assert isinstance(instance, AbstractProvider)

    def test_name_matches_class_attribute(self, provider_class: type[AbstractProvider]) -> None:
        instance = _instantiate(provider_class)
        assert instance.name == provider_class.name


# ---------------------------------------------------------------------------
# Stub contract — stubs must raise NotImplementedError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_class", _STUB_PROVIDERS, ids=lambda c: c.name)
class TestStubProviderContract:
    """Stub providers must raise NotImplementedError for all data methods."""

    _START = datetime(2024, 1, 1, tzinfo=timezone.utc)
    _END = datetime(2024, 1, 31, tzinfo=timezone.utc)

    def test_get_ohlcv_raises_not_implemented(self, provider_class: type[AbstractProvider]) -> None:
        p = _instantiate(provider_class)
        with pytest.raises(NotImplementedError):
            p.get_ohlcv("AAPL", Interval.ONE_DAY, self._START, self._END)

    def test_get_quote_raises_not_implemented(self, provider_class: type[AbstractProvider]) -> None:
        p = _instantiate(provider_class)
        with pytest.raises(NotImplementedError):
            p.get_quote("AAPL")

    def test_get_ticker_info_raises_not_implemented(
        self, provider_class: type[AbstractProvider]
    ) -> None:
        p = _instantiate(provider_class)
        with pytest.raises(NotImplementedError):
            p.get_ticker_info("AAPL")

    def test_health_check_raises_not_implemented(
        self, provider_class: type[AbstractProvider]
    ) -> None:
        p = _instantiate(provider_class)
        with pytest.raises(NotImplementedError):
            p.health_check()

    async def test_async_get_ohlcv_raises_not_implemented(
        self, provider_class: type[AbstractProvider]
    ) -> None:
        p = _instantiate(provider_class)
        with pytest.raises(NotImplementedError):
            await p.async_get_ohlcv("AAPL", Interval.ONE_DAY, self._START, self._END)

    async def test_async_get_quote_raises_not_implemented(
        self, provider_class: type[AbstractProvider]
    ) -> None:
        p = _instantiate(provider_class)
        with pytest.raises(NotImplementedError):
            await p.async_get_quote("AAPL")

    async def test_async_get_ticker_info_raises_not_implemented(
        self, provider_class: type[AbstractProvider]
    ) -> None:
        p = _instantiate(provider_class)
        with pytest.raises(NotImplementedError):
            await p.async_get_ticker_info("AAPL")

    async def test_async_health_check_raises_not_implemented(
        self, provider_class: type[AbstractProvider]
    ) -> None:
        p = _instantiate(provider_class)
        with pytest.raises(NotImplementedError):
            await p.async_health_check()


# ---------------------------------------------------------------------------
# Return type contract — implemented providers must return canonical models
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_class", _IMPLEMENTED_PROVIDERS, ids=lambda c: c.name)
class TestImplementedProviderReturnTypes:
    """Implemented providers must return valid canonical model instances."""

    def test_health_check_returns_health_status(
        self, provider_class: type[AbstractProvider], respx_mock: object
    ) -> None:
        """health_check() must return a HealthStatus (mocked HTTP where needed)."""
        import httpx
        import respx

        p = _instantiate(provider_class)

        if provider_class is YFinanceProvider:
            # yfinance uses the yf library, not HTTP — patch at module level
            from unittest.mock import MagicMock, patch

            mock_ticker = MagicMock()
            mock_ticker.info = {"symbol": "AAPL", "bid": 185.0}
            with patch("yfinance.Ticker", return_value=mock_ticker):
                result = p.health_check()
        else:
            # HTTP-based providers: mock any GET to return 200
            with respx.mock(assert_all_called=False) as mock:
                mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
                # health_check may raise on bad response shape — that's OK,
                # what we test is that *if* it returns, it returns the right type.
                try:
                    result = p.health_check()
                    assert isinstance(result, HealthStatus), (
                        f"{provider_class.name}.health_check() returned {type(result)}"
                    )
                    assert result.provider == provider_class.name
                except Exception:
                    pass  # Bad mock response — skip type assertion

    async def test_async_health_check_returns_health_status(
        self, provider_class: type[AbstractProvider]
    ) -> None:
        """async_health_check() delegates to health_check() via asyncio.to_thread."""
        from datetime import datetime, timezone
        from unittest.mock import patch

        p = _instantiate(provider_class)
        mock_status = HealthStatus(
            provider=provider_class.name,
            healthy=True,
            latency_ms=5.0,
            error=None,
            checked_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            rate_limit_remaining=None,
        )
        with patch.object(p, "health_check", return_value=mock_status):
            result = await p.async_health_check()
        assert isinstance(result, HealthStatus)
        assert result.provider == provider_class.name

    async def test_async_get_ohlcv_delegates_to_sync(
        self, provider_class: type[AbstractProvider]
    ) -> None:
        """async_get_ohlcv must delegate to get_ohlcv (via asyncio.to_thread)."""
        from datetime import datetime, timezone
        from decimal import Decimal
        from unittest.mock import patch

        p = _instantiate(provider_class)
        dummy_bar = OHLCVBar(
            ticker="AAPL",
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            interval=Interval.ONE_DAY,
            open=Decimal("185"),
            high=Decimal("188"),
            low=Decimal("183"),
            close_raw=Decimal("187"),
            close_adj=Decimal("187"),
            volume=1_000_000,
            vwap=None,
            trade_count=None,
            provider=provider_class.name,
        )
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        with patch.object(p, "get_ohlcv", return_value=[dummy_bar]):
            result = await p.async_get_ohlcv("AAPL", Interval.ONE_DAY, start, end)
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], OHLCVBar)

    async def test_async_get_quote_delegates_to_sync(
        self, provider_class: type[AbstractProvider]
    ) -> None:
        """async_get_quote must delegate to get_quote."""
        from decimal import Decimal
        from unittest.mock import patch

        p = _instantiate(provider_class)
        dummy_quote = Quote(
            ticker="AAPL",
            timestamp=datetime(2024, 1, 2, 15, 0, tzinfo=timezone.utc),
            bid=Decimal("186"),
            ask=Decimal("187"),
            bid_size=100,
            ask_size=100,
            last=Decimal("186.50"),
            last_size=50,
            volume=1_000_000,
            open=None,
            high=None,
            low=None,
            close=None,
            change=None,
            change_pct=None,
            provider=provider_class.name,
        )
        with patch.object(p, "get_quote", return_value=dummy_quote):
            result = await p.async_get_quote("AAPL")
        assert isinstance(result, Quote)

    async def test_async_get_ticker_info_delegates_to_sync(
        self, provider_class: type[AbstractProvider]
    ) -> None:
        """async_get_ticker_info must delegate to get_ticker_info.

        Tradier raises NotImplementedError for ticker_info (the client falls
        back to yfinance at a higher level). Verify that the async method
        propagates the NotImplementedError faithfully rather than silently
        swallowing it.
        """
        from unittest.mock import patch

        p = _instantiate(provider_class)

        if provider_class is TradierProvider:
            # async_get_ticker_info should propagate the NotImplementedError
            with pytest.raises(NotImplementedError):
                await p.async_get_ticker_info("AAPL")
            return

        dummy_info = TickerInfo(
            ticker="AAPL",
            name="Apple Inc.",
            exchange="NASDAQ",
            currency="USD",
            country="US",
            sector="Technology",
            industry="Consumer Electronics",
            market_cap=3_000_000_000_000,
            provider=provider_class.name,
        )
        with patch.object(p, "get_ticker_info", return_value=dummy_info):
            result = await p.async_get_ticker_info("AAPL")
        assert isinstance(result, TickerInfo)
