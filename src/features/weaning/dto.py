from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.features.weights.domain.dto import AnimalSummary


class WeaningInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    animal_id: UUID
    date: date
    weight_kg: Decimal = Field(gt=0, max_digits=7, decimal_places=2)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator('date')
    @classmethod
    def past_date(cls, value):
        if value > date.today():
            raise ValueError('Weaning date cannot be in the future')
        return value

    @field_validator('notes')
    @classmethod
    def normalize_notes(cls, value):
        return value or None


class WeaningOption(AnimalSummary):
    birth_date: date | None
    mother: AnimalSummary | None


class WeaningResponse(BaseModel):
    id: str
    animal: AnimalSummary
    mother: AnimalSummary | None
    date: date
    weight_kg: Decimal
    birth_date_snapshot: date | None
    age_days: int | None
    notes: str | None
    recorded_by: str


class WeaningPage(BaseModel):
    items: list[WeaningResponse]
    total: int
    offset: int
    limit: int
