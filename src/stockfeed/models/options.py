from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, field_validator


class GreeksSource(str, Enum):
    API = "api"
    CALCULATED = "calculated"


class Greeks(BaseModel):
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    rho: Decimal | None
    source: GreeksSource


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class OptionContract(BaseModel):
    symbol: str
    underlying: str
    expiration: date
    strike: Decimal
    option_type: OptionType
    bid: Decimal | None
    ask: Decimal | None
    last: Decimal | None
    volume: int | None
    open_interest: int | None
    implied_volatility: Decimal | None
    greeks: Greeks | None
    provider: str

    @field_validator("underlying")
    @classmethod
    def underlying_uppercase(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("underlying must not be empty")
        return v.upper()


class OptionChain(BaseModel):
    underlying: str
    expiration: date
    contracts: list[OptionContract]
    provider: str


class OptionQuote(BaseModel):
    symbol: str
    underlying: str
    bid: Decimal | None
    ask: Decimal | None
    last: Decimal | None
    volume: int | None
    open_interest: int | None
    implied_volatility: Decimal | None
    greeks: Greeks | None
    timestamp: datetime
    provider: str
