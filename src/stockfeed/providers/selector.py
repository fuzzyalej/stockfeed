"""Provider selection and failover ordering logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from stockfeed.models.interval import Interval

if TYPE_CHECKING:
    from stockfeed.providers.base import AbstractProvider
    from stockfeed.providers.health import HealthChecker
    from stockfeed.providers.rate_limiter import RateLimiter
    from stockfeed.providers.registry import ProviderRegistry


class ProviderSelector:
    """Select an ordered list of providers to try for a given request.

    Selection order
    ---------------
    1. If *preferred* is specified, that provider is tried first.
    2. Authenticated providers that support the requested *interval*,
       are not rate-limited, and are sorted by most-recently-healthy first.
    3. ``yfinance`` is always appended last as an unconditional fallback.

    Parameters
    ----------
    registry : ProviderRegistry
        Registry of all known provider classes.
    rate_limiter : RateLimiter
        Used to exclude rate-limited providers.
    health_checker : HealthChecker
        Used to sort providers by recency of successful health check.
    settings : StockFeedSettings
        Used to determine which providers have API keys configured.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        rate_limiter: RateLimiter,
        health_checker: HealthChecker,
        settings: object,  # StockFeedSettings — avoid circular import
    ) -> None:
        self._registry = registry
        self._rate_limiter = rate_limiter
        self._health_checker = health_checker
        self._settings = settings

    def select(
        self,
        ticker: str,
        interval: Interval,
        preferred: str | None = None,
    ) -> list[AbstractProvider]:
        """Return an ordered list of provider *instances* to try.

        Parameters
        ----------
        ticker : str
            Ticker symbol (used for logging only at this stage).
        interval : Interval
            Requested bar interval — providers that don't support it are excluded.
        preferred : str or None
            If given, that provider is placed first regardless of health state.

        Returns
        -------
        list[AbstractProvider]
            Non-empty list. ``yfinance`` is always the last entry.
        """
        all_providers = self._registry.all()
        ordered: list[AbstractProvider] = []
        seen: set[str] = set()

        # 1. Preferred provider first
        if preferred and preferred in all_providers:
            instance = self._instantiate(all_providers[preferred])
            if instance is not None:
                ordered.append(instance)
                seen.add(preferred)

        # 2. Auth-configured, interval-supported, not rate-limited
        #    sorted by most recently healthy
        candidates = []
        for name, cls in all_providers.items():
            if name in seen or name == "yfinance":
                continue
            if not self._has_auth(name):
                continue
            if interval not in cls.supported_intervals:
                continue
            if not self._rate_limiter.is_available(name):
                continue
            last = self._health_checker.last_status(name)
            last_healthy_at = last.checked_at if (last and last.healthy) else None
            candidates.append((last_healthy_at, name, cls))

        # Sort: providers with a recent healthy check first; never-checked last
        candidates.sort(key=lambda t: t[0] or __import__("datetime").datetime.min, reverse=True)
        for _, name, cls in candidates:
            instance = self._instantiate(cls)
            if instance is not None:
                ordered.append(instance)
                seen.add(name)

        # 3. yfinance always last
        if "yfinance" in all_providers and "yfinance" not in seen:
            instance = self._instantiate(all_providers["yfinance"])
            if instance is not None:
                ordered.append(instance)

        return ordered

    def _has_auth(self, provider_name: str) -> bool:
        """Return True if API key(s) for *provider_name* are configured."""
        s = self._settings
        key_map = {
            "tiingo": getattr(s, "tiingo_api_key", None),
            "finnhub": getattr(s, "finnhub_api_key", None),
            "twelvedata": getattr(s, "twelvedata_api_key", None),
            "alpaca": getattr(s, "alpaca_api_key", None),
            "tradier": getattr(s, "tradier_api_key", None),
            "coingecko": getattr(s, "coingecko_api_key", None),
        }
        return bool(key_map.get(provider_name))

    def _instantiate(self, cls: type[AbstractProvider]) -> AbstractProvider | None:
        """Instantiate a provider class, returning None on failure."""
        try:
            return cls()
        except Exception:
            return None
