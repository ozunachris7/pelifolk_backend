from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BreedInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)


class BreedResponse(BreedInput):
    id: int


class BreedShare(BaseModel):
    model_config = ConfigDict(extra='forbid')
    breed_id: int = Field(gt=0)
    percentage: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)


class AnimalInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, max_length=100)
    siniiga: str | None = Field(default=None, max_length=30)
    sex: Literal['male', 'female']
    birth_date: date | None = None
    origin: Literal['born_in_herd', 'purchased', 'donated', 'other'] = 'born_in_herd'
    mother_id: UUID | None = None
    father_id: UUID | None = None
    is_breeder: bool = False
    breeds: list[BreedShare] = Field(default_factory=list, max_length=100)

    @field_validator('name', 'siniiga', mode='before')
    @classmethod
    def empty_to_null(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode='after')
    def validate_animal(self):
        if not self.name and not self.siniiga:
            raise ValueError('Name or SINIIGA is required')
        if self.birth_date and self.birth_date > date.today():
            raise ValueError('Birth date cannot be in the future')
        if self.mother_id and self.mother_id == self.father_id:
            raise ValueError('Mother and father must be different')
        ids = [share.breed_id for share in self.breeds]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate breeds are not allowed')
        if self.breeds and sum(share.percentage for share in self.breeds) != Decimal('100'):
            raise ValueError('Breed percentages must total 100')
        return self


class BreedShareResponse(BaseModel):
    breed_id: int
    name: str
    percentage: Decimal


class ParentResponse(BaseModel):
    id: str
    name: str | None
    siniiga: str | None


class AnimalResponse(BaseModel):
    id: str
    name: str | None
    siniiga: str | None
    sex: str
    birth_date: date | None
    origin: str
    mother_id: str | None
    father_id: str | None
    is_breeder: bool
    created_at: datetime
    breeds: list[BreedShareResponse]
    mother: ParentResponse | None
    father: ParentResponse | None
    status: str = 'active'
    exit_date: date | None = None
    purity: Literal['pure', 'crossbred'] | None


class AnimalPage(BaseModel):
    items: list[AnimalResponse]
    total: int
    offset: int
    limit: int
