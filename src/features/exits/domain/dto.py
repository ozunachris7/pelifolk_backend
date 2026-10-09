from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

ExitType = Literal['sale', 'death', 'slaughter', 'transfer', 'theft', 'other']


class ExitInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    animal_id: UUID
    exit_type: ExitType
    date: date
    reason: str = Field(min_length=1, max_length=5000)

    @model_validator(mode='after')
    def past_date(self):
        if self.date > date.today():
            raise ValueError('Date cannot be in the future')
        return self


class AnimalSummary(BaseModel):
    id: str
    name: str | None
    siniiga: str | None


class ExitResponse(BaseModel):
    id: str
    animal: AnimalSummary
    exit_type: ExitType
    date: date
    reason: str | None
    recorded_by: str


class ExitPage(BaseModel):
    items: list[ExitResponse]
    total: int
    offset: int
    limit: int


class ExitHistory(BaseModel):
    animal: AnimalSummary
    items: list[ExitResponse]
