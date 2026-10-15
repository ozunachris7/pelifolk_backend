from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

TargetKind = Literal['animal', 'group', 'health_case']


class AllocationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: TargetKind
    target_id: UUID
    percentage: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)


class AllocationsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    allocations: list[AllocationInput] = Field(max_length=100)

    @model_validator(mode='after')
    def complete_distribution(self):
        if self.allocations and sum(r.percentage for r in self.allocations) != Decimal('100'):
            raise ValueError('Allocation percentages must total 100')
        keys = [(r.kind, r.target_id) for r in self.allocations]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate allocation targets')
        return self
