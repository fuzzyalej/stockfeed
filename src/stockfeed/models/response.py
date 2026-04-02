from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

from stockfeed.models.interval import Interval

T = TypeVar("T")


class StockFeedResponse(BaseModel, Generic[T]):
    data: T
    provider_used: str
    cache_hit: bool
    latency_ms: float
    timestamp: datetime  # When response was assembled
    interval: Interval | None
    ticker: str | None
