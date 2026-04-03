"""Unit tests for ProviderSelector."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from stockfeed.config import StockFeedSettings
from stockfeed.models.health import HealthStatus
from stockfeed.models.interval import Interval

# ---------------------------------------------------------------------------
# Helpers — concrete AbstractProvider subclasses
# ---------------------------------------------------------------------------
from stockfeed.providers.base import AbstractProvider
from stockfeed.providers.health import HealthChecker
from stockfeed.providers.rate_limiter import RateLimiter
from stockfeed.providers.registry import ProviderRegistry
from stockfeed.providers.selector import ProviderSelector


def _make_cls(name: str, requires_auth: bool = True) -> type[AbstractProvider]:
    """Return a minimal AbstractProvider subclass for testing."""

    _name = name
    _requires_auth = requires_auth

    class _P(AbstractProvider):
        supported_intervals = [Interval.ONE_DAY]

        def __init__(self, api_key: str = "", secret_key: str = "", **kwargs: object) -> None:
            pass

        def get_ohlcv(self, ticker, interval, start, end):  # type: ignore[override]
            return []

        def get_quote(self, ticker):  # type: ignore[override]
            return None

        def get_ticker_info(self, ticker):  # type: ignore[override]
            return None

        def health_check(self):  # type: ignore[override]
            return None

        async def async_get_ohlcv(self, ticker, interval, start, end):  # type: ignore[override]
            return []

        async def async_get_quote(self, ticker):  # type: ignore[override]
            return None

        async def async_get_ticker_info(self, ticker):  # type: ignore[override]
            return None

        async def async_health_check(self):  # type: ignore[override]
            return None

    _P.name = _name  # type: ignore[attr-defined]
    _P.requires_auth = _requires_auth  # type: ignore[attr-defined]
    return _P


def _make_selector(
    tmp_db_path: str,
    registry: ProviderRegistry | None = None,
    settings: StockFeedSettings | None = None,
) -> ProviderSelector:
    s = settings or StockFeedSettings(cache_path=tmp_db_path, log_level="WARNING")
    reg = registry or ProviderRegistry()
    return ProviderSelector(
        registry=reg,
        rate_limiter=RateLimiter(db_path=tmp_db_path),
        health_checker=HealthChecker(db_path=tmp_db_path),
        settings=s,
    )


# ---------------------------------------------------------------------------
# select() — ordering
# ---------------------------------------------------------------------------


class TestSelect:
    def test_preferred_provider_is_first(self, tmp_db_path: str) -> None:
        reg = ProviderRegistry()
        YFCls = _make_cls("yfinance", requires_auth=False)
        TiingoCls = _make_cls("tiingo", requires_auth=True)
        reg.register(YFCls)
        reg.register(TiingoCls)

        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            tiingo_api_key="key123",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, registry=reg, settings=settings)

        result = sel.select("AAPL", Interval.ONE_DAY, preferred="tiingo")
        assert len(result) >= 1
        assert result[0].name == "tiingo"

    def test_yfinance_always_last(self, tmp_db_path: str) -> None:
        reg = ProviderRegistry()
        YFCls = _make_cls("yfinance", requires_auth=False)
        reg.register(YFCls)

        sel = _make_selector(tmp_db_path, registry=reg)
        result = sel.select("AAPL", Interval.ONE_DAY)

        assert len(result) >= 1
        assert result[-1].name == "yfinance"

    def test_skips_unauthenticated_providers(self, tmp_db_path: str) -> None:
        reg = ProviderRegistry()
        YFCls = _make_cls("yfinance", requires_auth=False)
        TiingoCls = _make_cls("tiingo", requires_auth=True)
        reg.register(YFCls)
        reg.register(TiingoCls)

        # No tiingo key in settings
        sel = _make_selector(tmp_db_path, registry=reg)
        result = sel.select("AAPL", Interval.ONE_DAY)
        names = [p.name for p in result]

        assert "tiingo" not in names

    def test_skips_interval_not_supported(self, tmp_db_path: str) -> None:
        reg = ProviderRegistry()
        YFCls = _make_cls("yfinance", requires_auth=False)
        DayCls = _make_cls("dayonly", requires_auth=False)
        DayCls.supported_intervals = [Interval.ONE_DAY]  # type: ignore[attr-defined]
        reg.register(YFCls)
        reg.register(DayCls)

        sel = _make_selector(tmp_db_path, registry=reg)
        result = sel.select("AAPL", Interval.ONE_MINUTE)
        names = [p.name for p in result]

        assert "dayonly" not in names

    def test_skips_rate_limited_providers(self, tmp_db_path: str) -> None:
        reg = ProviderRegistry()
        YFCls = _make_cls("yfinance", requires_auth=False)
        TiingoCls = _make_cls("tiingo", requires_auth=True)
        reg.register(YFCls)
        reg.register(TiingoCls)

        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            tiingo_api_key="key123",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, registry=reg, settings=settings)

        with patch.object(sel._rate_limiter, "is_available", return_value=False):
            result = sel.select("AAPL", Interval.ONE_DAY)

        names = [p.name for p in result]
        assert "tiingo" not in names
        assert "yfinance" in names

    def test_result_is_list_of_instances(self, tmp_db_path: str) -> None:
        reg = ProviderRegistry()
        YFCls = _make_cls("yfinance", requires_auth=False)
        reg.register(YFCls)

        sel = _make_selector(tmp_db_path, registry=reg)
        result = sel.select("AAPL", Interval.ONE_DAY)

        assert isinstance(result, list)
        # Each element is an instance, not a class
        for p in result:
            assert not isinstance(p, type)

    def test_unknown_preferred_provider_ignored(self, tmp_db_path: str) -> None:
        reg = ProviderRegistry()
        YFCls = _make_cls("yfinance", requires_auth=False)
        reg.register(YFCls)

        sel = _make_selector(tmp_db_path, registry=reg)
        # "nonexistent" is not in registry — should not raise
        result = sel.select("AAPL", Interval.ONE_DAY, preferred="nonexistent")
        assert len(result) >= 1

    def test_sorted_by_most_recently_healthy(self, tmp_db_path: str) -> None:
        reg = ProviderRegistry()
        YFCls = _make_cls("yfinance", requires_auth=False)
        ACls = _make_cls("aaa", requires_auth=True)
        BCls = _make_cls("bbb", requires_auth=True)
        reg.register(YFCls)
        reg.register(ACls)
        reg.register(BCls)

        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            log_level="WARNING",
        )
        # monkeypatch to make both have "auth"
        settings.__dict__["aaa_api_key"] = "key"
        settings.__dict__["bbb_api_key"] = "key"

        sel = _make_selector(tmp_db_path, registry=reg, settings=settings)

        early = HealthStatus(
            provider="aaa",
            healthy=True,
            latency_ms=50.0,
            error=None,
            checked_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            rate_limit_remaining=None,
        )
        recent = HealthStatus(
            provider="bbb",
            healthy=True,
            latency_ms=10.0,
            error=None,
            checked_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            rate_limit_remaining=None,
        )

        def _last_status(name: str) -> HealthStatus | None:
            return {"aaa": early, "bbb": recent}.get(name)

        with (
            patch.object(sel._rate_limiter, "is_available", return_value=True),
            patch.object(sel._health_checker, "last_status", side_effect=_last_status),
            patch.object(sel, "_has_auth", return_value=True),
        ):
            result = sel.select("AAPL", Interval.ONE_DAY)

        # bbb has more recent healthy check — should come before aaa
        names = [p.name for p in result if p.name not in ("yfinance",)]
        bbb_pos = names.index("bbb") if "bbb" in names else 999
        aaa_pos = names.index("aaa") if "aaa" in names else 999
        assert bbb_pos < aaa_pos


# ---------------------------------------------------------------------------
# _has_auth()
# ---------------------------------------------------------------------------


class TestHasAuth:
    def test_tiingo_has_auth_with_key(self, tmp_db_path: str) -> None:
        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            tiingo_api_key="mykey",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, settings=settings)
        assert sel._has_auth("tiingo") is True

    def test_tiingo_no_auth_without_key(self, tmp_db_path: str) -> None:
        settings = StockFeedSettings(cache_path=tmp_db_path, log_level="WARNING")
        sel = _make_selector(tmp_db_path, settings=settings)
        assert sel._has_auth("tiingo") is False

    def test_finnhub_has_auth_with_key(self, tmp_db_path: str) -> None:
        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            finnhub_api_key="mykey",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, settings=settings)
        assert sel._has_auth("finnhub") is True

    def test_alpaca_has_auth_with_key(self, tmp_db_path: str) -> None:
        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            alpaca_api_key="mykey",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, settings=settings)
        assert sel._has_auth("alpaca") is True

    def test_tradier_has_auth_with_key(self, tmp_db_path: str) -> None:
        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            tradier_api_key="mykey",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, settings=settings)
        assert sel._has_auth("tradier") is True

    def test_coingecko_has_auth_with_key(self, tmp_db_path: str) -> None:
        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            coingecko_api_key="mykey",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, settings=settings)
        assert sel._has_auth("coingecko") is True

    def test_unknown_provider_no_auth(self, tmp_db_path: str) -> None:
        sel = _make_selector(tmp_db_path)
        assert sel._has_auth("unknown_provider_xyz") is False


# ---------------------------------------------------------------------------
# _instantiate()
# ---------------------------------------------------------------------------


class TestInstantiate:
    def test_instantiates_yfinance_no_key(self, tmp_db_path: str) -> None:
        from stockfeed.providers.yfinance.provider import YFinanceProvider

        sel = _make_selector(tmp_db_path)
        instance = sel._instantiate(YFinanceProvider)
        assert instance is not None
        assert instance.name == "yfinance"

    def test_instantiates_tiingo_with_key(self, tmp_db_path: str) -> None:
        from stockfeed.providers.tiingo.provider import TiingoProvider

        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            tiingo_api_key="testkey",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, settings=settings)
        instance = sel._instantiate(TiingoProvider)
        assert instance is not None
        assert instance.name == "tiingo"

    def test_instantiates_finnhub_with_key(self, tmp_db_path: str) -> None:
        from stockfeed.providers.finnhub.provider import FinnhubProvider

        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            finnhub_api_key="testkey",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, settings=settings)
        instance = sel._instantiate(FinnhubProvider)
        assert instance is not None

    def test_instantiates_twelvedata_with_key(self, tmp_db_path: str) -> None:
        from stockfeed.providers.twelvedata.provider import TwelvedataProvider

        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            twelvedata_api_key="testkey",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, settings=settings)
        instance = sel._instantiate(TwelvedataProvider)
        assert instance is not None

    def test_instantiates_alpaca_with_keys(self, tmp_db_path: str) -> None:
        from stockfeed.providers.alpaca.provider import AlpacaProvider

        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            alpaca_api_key="testkey",
            alpaca_secret_key="testsecret",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, settings=settings)
        instance = sel._instantiate(AlpacaProvider)
        assert instance is not None

    def test_instantiates_tradier_with_key(self, tmp_db_path: str) -> None:
        from stockfeed.providers.tradier.provider import TradierProvider

        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            tradier_api_key="testkey",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, settings=settings)
        instance = sel._instantiate(TradierProvider)
        assert instance is not None

    def test_instantiates_coingecko_with_key(self, tmp_db_path: str) -> None:
        from stockfeed.providers.coingecko.provider import CoingeckoProvider

        settings = StockFeedSettings(
            cache_path=tmp_db_path,
            coingecko_api_key="testkey",
            log_level="WARNING",
        )
        sel = _make_selector(tmp_db_path, settings=settings)
        instance = sel._instantiate(CoingeckoProvider)
        assert instance is not None

    def test_returns_none_on_instantiation_error(self, tmp_db_path: str) -> None:
        sel = _make_selector(tmp_db_path)

        class _Broken(AbstractProvider):
            name = "broken"  # type: ignore[assignment]
            supported_intervals = [Interval.ONE_DAY]  # type: ignore[assignment]
            requires_auth = False  # type: ignore[assignment]

            def __init__(self) -> None:
                raise RuntimeError("broken")

            def get_ohlcv(self, *a, **kw):  # type: ignore[override]
                ...
            def get_quote(self, *a, **kw):  # type: ignore[override]
                ...
            def get_ticker_info(self, *a, **kw):  # type: ignore[override]
                ...
            def health_check(self):  # type: ignore[override]
                ...
            async def async_get_ohlcv(self, *a, **kw):  # type: ignore[override]
                ...
            async def async_get_quote(self, *a, **kw):  # type: ignore[override]
                ...
            async def async_get_ticker_info(self, *a, **kw):  # type: ignore[override]
                ...
            async def async_health_check(self):  # type: ignore[override]
                ...

        result = sel._instantiate(_Broken)
        assert result is None
