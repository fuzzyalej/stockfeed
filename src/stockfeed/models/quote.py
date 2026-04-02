from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator


class Quote(BaseModel):
    ticker: str
    timestamp: datetime
    bid: Decimal | None
    ask: Decimal | None
    bid_size: int | None
    ask_size: int | None
    last: Decimal
    last_size: int | None
    volume: int | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    change: Decimal | None
    change_pct: Decimal | None
    provider: str

    @field_validator("ticker")
    @classmethod
    def ticker_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ticker must not be empty")
        return v.upper()
