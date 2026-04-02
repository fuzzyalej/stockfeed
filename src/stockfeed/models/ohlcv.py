from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from stockfeed.models.interval import Interval


class OHLCVBar(BaseModel):
    ticker: str
    timestamp: datetime  # Always UTC
    interval: Interval
    open: Decimal
    high: Decimal
    low: Decimal
    close_raw: Decimal  # Unadjusted close
    close_adj: Decimal | None  # Split/dividend adjusted — None if not provided
    volume: int
    vwap: Decimal | None  # If available
    trade_count: int | None  # If available
    provider: str

    @field_validator("ticker")
    @classmethod
    def ticker_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ticker must not be empty")
        return v.upper()
