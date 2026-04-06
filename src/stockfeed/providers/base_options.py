"""Abstract mixin for providers that support options data."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from stockfeed.models.options import OptionChain, OptionQuote


class AbstractOptionsProvider(ABC):
    """Mixin for options-capable providers.

    Inherit alongside AbstractProvider:
        class MyProvider(AbstractProvider, AbstractOptionsProvider): ...
    """

    @abstractmethod
    def get_option_expirations(self, ticker: str) -> list[date]:
        """Return available expiration dates for *ticker*."""

    @abstractmethod
    def get_options_chain(self, ticker: str, expiration: date) -> OptionChain:
        """Return all contracts for *ticker* at *expiration*."""

    @abstractmethod
    def get_option_quote(self, symbol: str) -> OptionQuote:
        """Return a live quote for the OCC option *symbol*."""

    @abstractmethod
    async def async_get_option_expirations(self, ticker: str) -> list[date]:
        """Async variant of :meth:`get_option_expirations`."""

    @abstractmethod
    async def async_get_options_chain(self, ticker: str, expiration: date) -> OptionChain:
        """Async variant of :meth:`get_options_chain`."""

    @abstractmethod
    async def async_get_option_quote(self, symbol: str) -> OptionQuote:
        """Async variant of :meth:`get_option_quote`."""
