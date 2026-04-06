"""Provider selection for options-capable providers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from stockfeed.providers.base_options import AbstractOptionsProvider

if TYPE_CHECKING:
    from stockfeed.providers.base import AbstractProvider
    from stockfeed.providers.health import HealthChecker
    from stockfeed.providers.rate_limiter import RateLimiter
    from stockfeed.providers.registry import ProviderRegistry


class OptionsProviderSelector:
    """Select an ordered list of options-capable providers.

    Mirrors ProviderSelector but filters to providers implementing
    AbstractOptionsProvider. yfinance is always the final fallback.

    Parameters
    ----------
    registry : ProviderRegistry
    rate_limiter : RateLimiter
    health_checker : HealthChecker
    settings : StockFeedSettings
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        rate_limiter: RateLimiter,
        health_checker: HealthChecker,
        settings: object,
    ) -> None:
        self._registry = registry
        self._rate_limiter = rate_limiter
        self._health_checker = health_checker
        self._settings = settings

    def select(
        self,
        preferred: str | None = None,
    ) -> list[AbstractProvider]:
        """Return an ordered list of options-capable provider instances.

        Order: preferred (if given) → auth-configured non-rate-limited
        sorted by health recency → yfinance fallback.
        """
        all_providers = self._registry.all()
        options_providers = {
            name: cls
            for name, cls in all_providers.items()
            if issubclass(cls, AbstractOptionsProvider)
        }

        ordered: list[AbstractProvider] = []
        seen: set[str] = set()

        # 1. Preferred first
        if preferred and preferred in options_providers:
            instance = self._instantiate(options_providers[preferred])
            if instance is not None:
                ordered.append(instance)
                seen.add(preferred)

        # 2. Auth-configured (or not requiring auth), not rate-limited,
        #    sorted by health recency
        candidates = []
        for name, cls in options_providers.items():
            if name in seen or name == "yfinance":
                continue
            requires_auth = getattr(cls, "requires_auth", True)
            if requires_auth and not self._has_auth(name):
                continue
            if not self._rate_limiter.is_available(name):
                continue
            last = self._health_checker.last_status(name)
            last_healthy_at = last.checked_at if (last and last.healthy) else None
            candidates.append((last_healthy_at, name, cls))

        candidates.sort(
            key=lambda t: t[0] or __import__("datetime").datetime.min,
            reverse=True,
        )
        for _, name, cls in candidates:
            instance = self._instantiate(cls)
            if instance is not None:
                ordered.append(instance)
                seen.add(name)

        # 3. yfinance always last
        if "yfinance" in options_providers and "yfinance" not in seen:
            instance = self._instantiate(options_providers["yfinance"])
            if instance is not None:
                ordered.append(instance)

        return ordered

    def _has_auth(self, provider_name: str) -> bool:
        s = self._settings
        key_map = {
            "tradier": getattr(s, "tradier_api_key", None),
            "alpaca": getattr(s, "alpaca_api_key", None),
            "finnhub": getattr(s, "finnhub_api_key", None),
        }
        return bool(key_map.get(provider_name))

    def _instantiate(self, cls: type) -> AbstractProvider | None:
        """Instantiate a provider class with credentials from settings."""
        name = cls.name
        s = self._settings
        try:
            if name == "tradier":
                return cls(api_key=getattr(s, "tradier_api_key", "") or "")  # type: ignore[call-arg]
            if name == "alpaca":
                return cls(  # type: ignore[call-arg]
                    api_key=getattr(s, "alpaca_api_key", "") or "",
                    secret_key=getattr(s, "alpaca_secret_key", "") or "",
                )
            if name == "finnhub":
                return cls(api_key=getattr(s, "finnhub_api_key", "") or "")  # type: ignore[call-arg]
            return cls()
        except Exception:
            return None
