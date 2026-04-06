import pytest

from stockfeed.providers.base_options import AbstractOptionsProvider


def test_abstract_options_provider_cannot_be_instantiated():
    with pytest.raises(TypeError):
        AbstractOptionsProvider()


def test_concrete_provider_must_implement_all_methods():
    """A class that only partially implements the mixin should raise TypeError."""

    class Partial(AbstractOptionsProvider):
        def get_option_expirations(self, ticker):
            return []

        # Missing get_options_chain, get_option_quote, async variants

    with pytest.raises(TypeError):
        Partial()


def test_concrete_provider_full_implementation():
    class Full(AbstractOptionsProvider):
        def get_option_expirations(self, ticker):
            return []

        def get_options_chain(self, ticker, expiration): ...
        def get_option_quote(self, symbol): ...
        async def async_get_option_expirations(self, ticker):
            return []

        async def async_get_options_chain(self, ticker, expiration): ...
        async def async_get_option_quote(self, symbol): ...

    instance = Full()
    assert isinstance(instance, AbstractOptionsProvider)
