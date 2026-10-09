from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,Field,ConfigDict,model_validator

class EventInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    animal_id: UUID
    date: date
    notes: str | None = Field(default=None,max_length=5000)
    @model_validator(mode='after')
    def past(self):
        if self.date>date.today():
            raise ValueError('Date cannot be in the future')
        return self

class MatingInput(EventInput):
    male_id: UUID

class PregnancyInput(EventInput):
    result: Literal['pregnant','not_pregnant','uncertain']
    mating_event_id: UUID | None = None

class OffspringInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    name: str | None = Field(default=None,max_length=100)
    siniiga: str | None = Field(default=None,max_length=30)
    sex: Literal['male','female']
    alive: bool = True
    birth_weight_kg: Decimal | None = Field(default=None,gt=0,max_digits=5,decimal_places=2)
    @model_validator(mode='after')
    def identity(self):
        if not self.name and not self.siniiga:
            raise ValueError('Name or SINIIGA is required')
        return self

class BirthInput(EventInput):
    birth_type_id: int = Field(gt=0)
    father_id: UUID | None = None
    offspring: list[OffspringInput] = Field(min_length=1,max_length=20)
    @model_validator(mode='after')
    def unique_tags(self):
        tags=[o.siniiga.lower() for o in self.offspring if o.siniiga]
        if len(tags)!=len(set(tags)):
            raise ValueError('Duplicate offspring SINIIGA')
        return self

class AnimalSummary(BaseModel):
    id: str
    name: str | None
    siniiga: str | None
    sex: str

class OffspringResponse(BaseModel):
    animal: AnimalSummary
    alive: bool
    birth_weight_kg: Decimal | None

class BreedingEvent(BaseModel):
    id: str
    kind: Literal['mating','pregnancy','birth']
    animal: AnimalSummary
    date: date
    notes: str | None
    recorded_by: str
    male: AnimalSummary | None = None
    result: str | None = None
    mating_event_id: str | None = None
    birth_type: str | None = None
    offspring: list[OffspringResponse] = Field(default_factory=list)

class EventPage(BaseModel):
    items: list[BreedingEvent]
    total: int
    offset: int
    limit: int

class BreedingHistory(BaseModel):
    animal: AnimalSummary
    items: list[BreedingEvent]

class BirthTypeResponse(BaseModel):
    id: int
    name: str
