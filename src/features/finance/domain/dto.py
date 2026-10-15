from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

CategoryKind = Literal['expense', 'income']


class CategoryInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)


class CategoryResponse(CategoryInput):
    id: int


class SupplierInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = Field(default=None, max_length=190)
    address: str | None = Field(default=None, max_length=5000)
    active: bool = True

    @field_validator('phone','email','address', mode='before')
    @classmethod
    def empty_to_null(cls, value):
        return value.strip() or None if isinstance(value,str) else value


class SupplierResponse(SupplierInput):
    id: str


class SupplierPage(BaseModel):
    items: list[SupplierResponse]
    total: int
    offset: int
    limit: int


class MoneyInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    category_id: int = Field(gt=0)
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    date: date
    description: str | None = Field(default=None, max_length=5000)

    @model_validator(mode='after')
    def past_date(self):
        if self.date > date.today():
            raise ValueError('Date cannot be in the future')
        return self


class ExpenseInput(MoneyInput):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    supplier_id: UUID | None = None


class IncomeInput(MoneyInput):
    exit_event_id: UUID | None = None


class SaleResponse(BaseModel):
    id: str
    animal_id: str
    animal_name: str | None
    siniiga: str | None
    date: date


class MoneyResponse(BaseModel):
    id: str
    category: CategoryResponse
    amount: Decimal
    date: date
    description: str | None
    supplier: SupplierResponse | None = None
    sale: SaleResponse | None = None
    allocation_count: int = 0


class MoneyPage(BaseModel):
    items: list[MoneyResponse]
    total: int
    offset: int
    limit: int


class FinanceSummary(BaseModel):
    income_total: Decimal
    expense_total: Decimal
    balance: Decimal
    income_count: int
    expense_count: int
