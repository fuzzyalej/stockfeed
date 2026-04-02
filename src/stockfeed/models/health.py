from datetime import datetime

from pydantic import BaseModel


class HealthStatus(BaseModel):
    provider: str
    healthy: bool
    latency_ms: float | None
    error: str | None
    checked_at: datetime
    rate_limit_remaining: int | None
