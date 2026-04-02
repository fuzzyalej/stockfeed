from pydantic import BaseModel, field_validator


class TickerInfo(BaseModel):
    ticker: str
    name: str
    exchange: str
    currency: str
    country: str | None
    sector: str | None
    industry: str | None
    market_cap: int | None
    provider: str

    @field_validator("ticker")
    @classmethod
    def ticker_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ticker must not be empty")
        return v.upper()
