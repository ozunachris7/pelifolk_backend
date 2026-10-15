from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeedInput(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    name: str = Field(min_length=1,max_length=150)
    unit_id: int = Field(gt=0)


class FeedResponse(FeedInput):
    id: str
    unit_code: str
    current_unit_cost: Decimal | None = None
    current_price_from: date | None = None


class UnitResponse(BaseModel):
    id: int
    code: str


class PriceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    effective_from: date
    unit_cost: Decimal = Field(ge=0,max_digits=12,decimal_places=4)


class FeedCreateInput(FeedInput):
    initial_price: PriceInput | None = None


class PriceResponse(PriceInput):
    pass


class FeedingInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    animal_id: UUID | None = None
    group_id: UUID | None = None
    feed_id: UUID
    date: date
    quantity: Decimal = Field(gt=0,max_digits=10,decimal_places=2)

    @model_validator(mode='after')
    def valid_target_and_date(self):
        if (self.animal_id is None) == (self.group_id is None):
            raise ValueError('Choose exactly one animal or group')
        if self.date > date.today():
            raise ValueError('Date cannot be in the future')
        return self


class TargetResponse(BaseModel):
    id: str
    name: str | None
    siniiga: str | None = None


class FeedingResponse(BaseModel):
    id: str
    animal: TargetResponse | None
    group: TargetResponse | None
    feed: FeedResponse
    date: date
    quantity: Decimal
    unit_cost: Decimal | None
    price_from: date | None
    cost: Decimal | None


class FeedingPage(BaseModel):
    items: list[FeedingResponse]
    total: int
    offset: int
    limit: int
    total_cost: Decimal
    unpriced_count: int


class FeedPage(BaseModel):
    items: list[FeedResponse]
    total: int
    offset: int
    limit: int
