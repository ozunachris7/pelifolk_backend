from datetime import date
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NamedInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    active: bool = True

    @field_validator('description', mode='before')
    @classmethod
    def clean_description(cls, value):
        return value.strip() or None if isinstance(value, str) else value


class TypeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)


class TypeResponse(TypeInput):
    id: int


class LocationInput(NamedInput):
    location_type_id: int = Field(gt=0)


class LocationResponse(LocationInput):
    id: str
    location_type_name: str


class GroupResponse(NamedInput):
    id: str
    member_count: int


class EffectiveDate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    effective_date: date

    @field_validator('effective_date')
    @classmethod
    def not_future(cls, value):
        if value > date.today():
            raise ValueError('Future movements are not supported')
        return value


class AssignmentInput(EffectiveDate):
    animal_ids: list[UUID] = Field(min_length=1, max_length=100)
    move_existing: bool = False

    @model_validator(mode='after')
    def distinct_animals(self):
        if len(set(self.animal_ids)) != len(self.animal_ids):
            raise ValueError('Duplicate animals are not allowed')
        return self


class MembershipResponse(BaseModel):
    group_id: str
    group_name: str
    animal_id: str
    animal_name: str | None
    siniiga: str | None
    start_date: date
    end_date: date | None


class MembershipPage(BaseModel):
    items: list[MembershipResponse]
    total: int
    offset: int
    limit: int


class AnimalOption(BaseModel):
    id: str
    name: str | None
    siniiga: str | None
    group_id: str | None
    group_name: str | None


class AnimalOptionPage(BaseModel):
    items: list[AnimalOption]
    total: int
