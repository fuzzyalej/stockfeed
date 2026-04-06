from unittest.mock import MagicMock

from stockfeed.providers.base import AbstractProvider
from stockfeed.providers.base_options import AbstractOptionsProvider
from stockfeed.providers.options_selector import OptionsProviderSelector


class _OptionsCapable(AbstractProvider, AbstractOptionsProvider):
    name = "capable"
    supported_intervals = []
    requires_auth = False

    def get_ohlcv(self, *a): ...
    def get_quote(self, *a): ...
    def get_ticker_info(self, *a): ...
    def health_check(self): ...
    async def async_get_ohlcv(self, *a): ...
    async def async_get_quote(self, *a): ...
    async def async_get_ticker_info(self, *a): ...
    async def async_health_check(self): ...
    def get_option_expirations(self, ticker):
        return []

    def get_options_chain(self, ticker, expiration): ...
    def get_option_quote(self, symbol): ...
    async def async_get_option_expirations(self, ticker):
        return []

    async def async_get_options_chain(self, ticker, expiration): ...
    async def async_get_option_quote(self, symbol): ...


class _StockOnly(AbstractProvider):
    name = "stock_only"
    supported_intervals = []
    requires_auth = False

    def get_ohlcv(self, *a): ...
    def get_quote(self, *a): ...
    def get_ticker_info(self, *a): ...
    def health_check(self): ...
    async def async_get_ohlcv(self, *a): ...
    async def async_get_quote(self, *a): ...
    async def async_get_ticker_info(self, *a): ...
    async def async_health_check(self): ...


def _make_registry(providers: dict):
    r = MagicMock()
    r.all.return_value = providers
    return r


def test_selector_excludes_non_options_providers():
    registry = _make_registry({"capable": _OptionsCapable, "stock_only": _StockOnly})
    rate_limiter = MagicMock()
    rate_limiter.is_available.return_value = True
    health_checker = MagicMock()
    health_checker.last_status.return_value = None
    settings = MagicMock()
    settings.tradier_api_key = None
    settings.alpaca_api_key = None
    settings.finnhub_api_key = None

    selector = OptionsProviderSelector(
        registry=registry,
        rate_limiter=rate_limiter,
        health_checker=health_checker,
        settings=settings,
    )
    providers = selector.select()
    names = [p.name for p in providers]
    assert "capable" in names
    assert "stock_only" not in names


def test_selector_yfinance_always_last():
    class _YF(_OptionsCapable):
        name = "yfinance"
        requires_auth = False

    class _Tradier(_OptionsCapable):
        name = "tradier"
        requires_auth = True

    registry = _make_registry({"yfinance": _YF, "tradier": _Tradier})
    rate_limiter = MagicMock()
    rate_limiter.is_available.return_value = True
    health_checker = MagicMock()
    health_checker.last_status.return_value = None
    settings = MagicMock()
    settings.tradier_api_key = "key"
    settings.alpaca_api_key = None
    settings.finnhub_api_key = None

    selector = OptionsProviderSelector(
        registry=registry,
        rate_limiter=rate_limiter,
        health_checker=health_checker,
        settings=settings,
    )
    providers = selector.select()
    assert providers[-1].name == "yfinance"


def test_selector_preferred_provider_first():
    class _YF(_OptionsCapable):
        name = "yfinance"
        requires_auth = False

    class _Tradier(_OptionsCapable):
        name = "tradier"
        requires_auth = True

    registry = _make_registry({"yfinance": _YF, "tradier": _Tradier})
    rate_limiter = MagicMock()
    rate_limiter.is_available.return_value = True
    health_checker = MagicMock()
    health_checker.last_status.return_value = None
    settings = MagicMock()
    settings.tradier_api_key = "key"
    settings.alpaca_api_key = None
    settings.finnhub_api_key = None

    selector = OptionsProviderSelector(
        registry=registry,
        rate_limiter=rate_limiter,
        health_checker=health_checker,
        settings=settings,
    )
    providers = selector.select(preferred="yfinance")
    assert providers[0].name == "yfinance"
