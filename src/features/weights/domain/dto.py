from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class WeightInput(BaseModel):
    animal_id: UUID
    date: date
    weight_kg: Decimal = Field(gt=0, max_digits=7, decimal_places=2)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator('date')
    @classmethod
    def past_date(cls, value):
        if value > date.today():
            raise ValueError('Weight date cannot be in the future')
        return value

    @field_validator('notes')
    @classmethod
    def trim_notes(cls, value):
        return value.strip() or None if value is not None else None


class AnimalSummary(BaseModel):
    id: str
    name: str | None
    siniiga: str | None


class WeightResponse(BaseModel):
    is_weaning: bool = False
    id: str
    animal: AnimalSummary
    date: date
    weight_kg: Decimal
    notes: str | None
    recorded_by: str


class WeightPage(BaseModel):
    items: list[WeightResponse]
    total: int
    offset: int
    limit: int


class WeightHistory(BaseModel):
    animal: AnimalSummary
    items: list[WeightResponse]
