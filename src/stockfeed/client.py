"""Synchronous StockFeedClient — implemented in Phase 3."""

from stockfeed.config import StockFeedSettings


class StockFeedClient:
    """Synchronous client for stockfeed. Full implementation in Phase 3."""

    def __init__(self, settings: StockFeedSettings | None = None) -> None:
        self.settings = settings or StockFeedSettings()
