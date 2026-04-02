"""Provider registry — maps provider names to their classes."""

from __future__ import annotations

import importlib.metadata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stockfeed.providers.base import AbstractProvider


class ProviderRegistry:
    """Map provider name strings to :class:`AbstractProvider` classes.

    Providers can be registered explicitly via :meth:`register` or
    discovered automatically from the ``stockfeed.providers`` entry-point
    group, allowing third-party packages to add providers without
    modifying stockfeed itself.
    """

    def __init__(self) -> None:
        self._registry: dict[str, type[AbstractProvider]] = {}

    def register(self, provider_class: type[AbstractProvider]) -> None:
        """Register a provider class under its ``name`` attribute.

        Parameters
        ----------
        provider_class : type[AbstractProvider]
            The class to register. Must have a ``name`` class attribute.
        """
        self._registry[provider_class.name] = provider_class

    def get(self, name: str) -> type[AbstractProvider]:
        """Return the provider class registered under *name*.

        Parameters
        ----------
        name : str
            Provider identifier (e.g. ``"tiingo"``).

        Returns
        -------
        type[AbstractProvider]

        Raises
        ------
        KeyError
            If no provider with *name* is registered.
        """
        if name not in self._registry:
            available = ", ".join(sorted(self._registry))
            raise KeyError(
                f"Unknown provider '{name}'. Available: {available or 'none registered'}"
            )
        return self._registry[name]

    def all(self) -> dict[str, type[AbstractProvider]]:
        """Return a snapshot of the full registry."""
        return dict(self._registry)

    def discover_entry_points(self) -> None:
        """Load providers registered under the ``stockfeed.providers`` entry-point group.

        Third-party packages add providers by declaring in their
        ``pyproject.toml``::

            [project.entry-points."stockfeed.providers"]
            myprovider = "mypkg.provider:MyProvider"
        """
        for ep in importlib.metadata.entry_points(group="stockfeed.providers"):
            provider_class = ep.load()
            self.register(provider_class)


# Module-level singleton used by the rest of the library
_default_registry = ProviderRegistry()


def get_default_registry() -> ProviderRegistry:
    """Return the shared default :class:`ProviderRegistry` instance."""
    return _default_registry
