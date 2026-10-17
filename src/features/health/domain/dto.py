from datetime import date, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from src.features.weights.domain.dto import AnimalSummary

CaseStatus = Literal['open', 'under_treatment', 'closed']

class PastDateInput(BaseModel):
    @field_validator('date', 'start_date', 'closed_date', check_fields=False)
    @classmethod
    def not_future(cls, value):
        if value and value > date.today():
            raise ValueError('Date cannot be in the future')
        return value

class ObservationInput(PastDateInput):
    animal_id: UUID
    date: date
    observation: str = Field(min_length=1, max_length=5000)

    @field_validator('observation', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

class CaseInput(PastDateInput):
    observation_id: UUID | None = None
    animal_id: UUID
    start_date: date
    reason: str = Field(min_length=1, max_length=255)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator('reason', 'notes', mode='before')
    @classmethod
    def trim(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

class CaseStatusInput(PastDateInput):
    expected_status: CaseStatus
    status: CaseStatus
    closed_date: date | None = None

    @model_validator(mode='after')
    def closure(self):
        if (self.status == 'closed') != (self.closed_date is not None):
            raise ValueError('Closed date is required only for closed cases')
        return self

class LinkedCase(BaseModel):
    id: str
    reason: str
    status: CaseStatus
    start_date: date


class ObservationCaseInput(BaseModel):
    model_config = {'extra': 'forbid'}
    case_id: UUID


class ObservationResponse(BaseModel):
    id: str
    animal: AnimalSummary
    date: date
    observation: str
    recorded_by: str
    health_case: LinkedCase | None = None

class ObservationPage(BaseModel):
    items: list[ObservationResponse]
    total: int
    offset: int
    limit: int

class CaseResponse(BaseModel):
    id: str
    animal: AnimalSummary
    reason: str
    status: CaseStatus
    start_date: date
    closed_date: date | None
    notes: str | None

class CasePage(BaseModel):
    items: list[CaseResponse]
    total: int
    offset: int
    limit: int

class CaseActivity(BaseModel):
    date: str
    recorded_by: str
    action: str
    previous_status: CaseStatus | None
    status: CaseStatus
    closed_date: date | None

class DiagnosisInput(PastDateInput):
    date: date
    diagnosis: str = Field(min_length=1, max_length=5000)
    severity: Literal['mild', 'moderate', 'severe', 'critical']

    @field_validator('diagnosis', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

class DiagnosisResponse(BaseModel):
    id: str
    health_case_id: str
    animal: AnimalSummary
    date: date
    diagnosis: str
    severity: Literal['mild', 'moderate', 'severe', 'critical']
    recorded_by: str

class CatalogItem(BaseModel):
    id: int
    name: str

class UnitResponse(BaseModel):
    id: int
    code: str

class TreatmentCatalogs(BaseModel):
    product_types: list[CatalogItem]
    units: list[UnitResponse]
    routes: list[CatalogItem]

class IngredientInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)


class IngredientResponse(BaseModel):
    id: int
    name: str
    product_count: int


class IngredientPage(BaseModel):
    items: list[IngredientResponse]
    total: int
    offset: int
    limit: int


class ProductPriceInput(BaseModel):
    expected_unit_id: int | None = Field(default=None, gt=0)
    model_config = ConfigDict(extra='forbid')
    effective_from: date
    cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class ProductInput(BaseModel):
    initial_price: ProductPriceInput | None = None
    name: str = Field(min_length=1, max_length=150)
    product_type_id: int = Field(gt=0)
    unit_id: int = Field(gt=0)
    withdrawal_days: int = Field(default=0, ge=0, le=2147483647)
    active: bool = True

    # Omission preserves composition for older API clients; [] explicitly clears it.
    ingredient_ids: list[int] | None = Field(default=None, max_length=100)

    @field_validator('ingredient_ids')
    @classmethod
    def valid_ingredients(cls, value):
        if value is not None and (any(i <= 0 for i in value) or len(set(value)) != len(value)):
            raise ValueError('Ingredient IDs must be positive and unique')
        return value

    @field_validator('name', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

class ProductResponse(BaseModel):
    id: str
    name: str
    product_type_id: int
    product_type_name: str
    unit_id: int
    unit_code: str
    withdrawal_days: int
    active: bool
    ingredients: list[CatalogItem] = Field(default_factory=list)
    current_price: ProductPriceInput | None = None

class ProductPage(BaseModel):
    items: list[ProductResponse]
    total: int
    offset: int
    limit: int

class TreatmentDetails(PastDateInput):
    start_date: date
    dose_value: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    dose_unit_id: int = Field(gt=0)
    route_id: int = Field(gt=0)
    frequency_hours: int | None = Field(default=None, gt=0, le=2147483647)
    duration_days: int = Field(gt=0, le=3650)

    @model_validator(mode='after')
    def valid_end(self):
        try:
            self.start_date + timedelta(days=self.duration_days)
        except OverflowError:
            raise ValueError('Treatment duration exceeds supported dates')
        return self

class TreatmentInput(TreatmentDetails):
    product_id: UUID

class ProgramApplicationInput(TreatmentDetails):
    animal_id: UUID

class ProgramInput(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    product_id: UUID
    interval_days: int = Field(gt=0, le=36500)
    minimum_age_days: int = Field(default=0, ge=0, le=36500)
    sex: Literal['male','female'] | None = None
    notice_days: int = Field(default=0, ge=0, le=36500)
    active: bool = True

    @field_validator('name', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value,str) else value

class ProgramResponse(BaseModel):
    id: str
    name: str
    product: ProductResponse
    interval_days: int
    minimum_age_days: int
    sex: Literal['male','female'] | None
    notice_days: int
    active: bool

class ProgramPage(BaseModel):
    items: list[ProgramResponse]
    total: int
    offset: int
    limit: int

class ProgramNotice(BaseModel):
    animal: AnimalSummary
    birth_date: date | None
    last_application: date | None
    due_date: date | None
    days_remaining: int | None
    status: Literal['overdue','due','upcoming','scheduled','missing_birth_date']
    can_apply: bool

class ProgramSchedule(BaseModel):
    program: ProgramResponse
    as_of: date
    items: list[ProgramNotice]
    total: int
    offset: int
    limit: int

class TreatmentResponse(BaseModel):
    id: str
    health_case_id: str | None
    program_id: str | None
    program_name: str | None
    animal: AnimalSummary
    product: ProductResponse
    start_date: date
    end_date: date
    last_day: date
    dose_value: Decimal
    dose_unit_id: int
    dose_unit_code: str
    route_id: int
    route_name: str
    frequency_hours: int | None
    duration_days: int
    recorded_by: str

Evolution = Literal['improved', 'unchanged', 'worsened', 'recovered']
TreatmentResult = Literal['not_assessed', 'effective', 'partially_effective', 'not_effective']

class FollowupInput(PastDateInput):
    model_config = {'extra': 'forbid'}
    date: date
    evolution: Evolution
    treatment_result: TreatmentResult = 'not_assessed'
    notes: str = Field(min_length=1, max_length=5000)
    next_review_date: date | None = None

    @field_validator('notes', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode='after')
    def review_date(self):
        if self.next_review_date and self.next_review_date < self.date:
            raise ValueError('Review date cannot be before followup')
        return self

class FollowupResponse(BaseModel):
    id: str
    health_case_id: str
    animal: AnimalSummary
    date: date
    evolution: Evolution
    treatment_result: TreatmentResult
    notes: str
    next_review_date: date | None
    recorded_by: str
    created_at: str

class ReviewResponse(BaseModel):
    case: CaseResponse
    followup: FollowupResponse
    next_review_date: date
    status: Literal['overdue', 'due', 'upcoming']

class ReviewPage(BaseModel):
    items: list[ReviewResponse]
    total: int
    offset: int
    limit: int
    as_of: date

class CaseDetail(BaseModel):
    observations: list[ObservationResponse] = Field(default_factory=list)
    case: CaseResponse
    activity: list[CaseActivity]
    diagnoses: list[DiagnosisResponse]
    treatments: list[TreatmentResponse]
    followups: list[FollowupResponse] = Field(default_factory=list)

class HealthHistory(BaseModel):
    animal: AnimalSummary
    observations: list[ObservationResponse]
    cases: list[CaseResponse]
    diagnoses: list[DiagnosisResponse]
    treatments: list[TreatmentResponse]
    followups: list[FollowupResponse] = Field(default_factory=list)
