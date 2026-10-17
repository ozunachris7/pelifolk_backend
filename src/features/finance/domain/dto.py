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
    animal_id: UUID | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    exit_event_id: UUID | None = None
    pricing_mode: Literal['total', 'per_kg'] = 'total'
    weight_event_id: UUID | None = None
    price_per_kg: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)

    @model_validator(mode='after')
    def pricing(self):
        if self.animal_id and self.exit_event_id:
            raise ValueError('Use an animal or a sale link, not both')
        if self.pricing_mode == 'per_kg':
            if not self.exit_event_id or not self.weight_event_id or self.price_per_kg is None:
                raise ValueError('Per kilogram pricing requires a sale, weight event and price')
        elif self.amount is None or self.weight_event_id is not None or self.price_per_kg is not None:
            raise ValueError('Total pricing requires an amount and no kilogram pricing fields')
        return self


class SaleWeightResponse(BaseModel):
    id: str
    date: date
    weight_kg: Decimal


class SalePricingResponse(BaseModel):
    weight_event_id: str
    weight_kg: Decimal
    price_per_kg: Decimal


class SaleResponse(BaseModel):
    id: str
    animal_id: str
    animal_name: str | None
    siniiga: str | None
    date: date


class IncomeAnimalResponse(BaseModel):
    id: str
    name: str | None
    siniiga: str | None


class MoneyResponse(BaseModel):
    id: str
    category: CategoryResponse
    amount: Decimal
    date: date
    description: str | None
    supplier: SupplierResponse | None = None
    sale: SaleResponse | None = None
    animal: IncomeAnimalResponse | None = None
    allocation_count: int = 0
    sale_pricing: SalePricingResponse | None = None


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
