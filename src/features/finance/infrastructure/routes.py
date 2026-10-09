from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.finance.domain.dto import (CategoryInput, CategoryKind, CategoryResponse, ExpenseInput,
    FinanceSummary, IncomeInput, MoneyPage, MoneyResponse, SaleResponse, SupplierInput, SupplierPage, SupplierResponse)
from .repository import SQLFinanceRepository

router = APIRouter(prefix='/finance',tags=['Finance'])


def repository(db: Session=Depends(get_db,scope='function')):
    return SQLFinanceRepository(db)


def date_range(date_from: date | None=None, date_to: date | None=None):
    if date_from and date_to and date_from > date_to:
        raise ApplicationError('Invalid finance date range',422)
    return date_from,date_to


@router.get('/summary',response_model=FinanceSummary)
def summary(dates=Depends(date_range),actor=Depends(require_permission('finance:read')),repo=Depends(repository)):
    return repo.summary(*dates)


@router.get('/categories/{kind}',response_model=list[CategoryResponse])
def categories(kind: CategoryKind,actor=Depends(require_permission('finance:read')),repo=Depends(repository)):
    return repo.categories(kind)


@router.post('/categories/{kind}',response_model=CategoryResponse,status_code=201)
def create_category(kind: CategoryKind,data: CategoryInput,actor=Depends(require_permission('finance:write')),repo=Depends(repository)):
    return repo.save_category(kind,data,actor)


@router.put('/categories/{kind}/{category_id}',response_model=CategoryResponse)
def update_category(kind: CategoryKind,data: CategoryInput,category_id: int=Path(gt=0),actor=Depends(require_permission('finance:write')),repo=Depends(repository)):
    return repo.save_category(kind,data,actor,category_id)


@router.delete('/categories/{kind}/{category_id}',status_code=204)
def delete_category(kind: CategoryKind,category_id: int=Path(gt=0),actor=Depends(require_permission('finance:write')),repo=Depends(repository)):
    repo.delete_category(kind,category_id,actor)
    return Response(status_code=204)


@router.get('/suppliers',response_model=SupplierPage)
def suppliers(q: str=Query('',max_length=100),active: bool | None=None,offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),actor=Depends(require_permission('finance:read')),repo=Depends(repository)):
    return repo.suppliers(q.strip(),active,offset,limit)


@router.post('/suppliers',response_model=SupplierResponse,status_code=201)
def create_supplier(data: SupplierInput,actor=Depends(require_permission('finance:write')),repo=Depends(repository)):
    return repo.save_supplier(data,actor)


@router.put('/suppliers/{supplier_id}',response_model=SupplierResponse)
def update_supplier(supplier_id: UUID,data: SupplierInput,actor=Depends(require_permission('finance:write')),repo=Depends(repository)):
    return repo.save_supplier(data,actor,str(supplier_id))


@router.get('/sale-options',response_model=list[SaleResponse])
def sale_options(q: str=Query('',max_length=100),income_id: UUID | None=None,actor=Depends(require_permission('finance:read')),repo=Depends(repository)):
    return repo.sale_options(q.strip(),str(income_id) if income_id else None)


@router.get('/expenses',response_model=MoneyPage)
def expenses(q: str=Query('',max_length=100),category_id: int | None=Query(None,gt=0),dates=Depends(date_range),offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),actor=Depends(require_permission('finance:read')),repo=Depends(repository)):
    return repo.money_page('expense',q.strip(),category_id,*dates,offset,limit)


@router.get('/incomes',response_model=MoneyPage)
def incomes(q: str=Query('',max_length=100),category_id: int | None=Query(None,gt=0),dates=Depends(date_range),offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),actor=Depends(require_permission('finance:read')),repo=Depends(repository)):
    return repo.money_page('income',q.strip(),category_id,*dates,offset,limit)


@router.post('/expenses',response_model=MoneyResponse,status_code=201)
def create_expense(data: ExpenseInput,actor=Depends(require_permission('finance:write')),repo=Depends(repository)):
    return repo.save_money('expense',data,actor)


@router.put('/expenses/{record_id}',response_model=MoneyResponse)
def update_expense(record_id: UUID,data: ExpenseInput,actor=Depends(require_permission('finance:write')),repo=Depends(repository)):
    return repo.save_money('expense',data,actor,str(record_id))


@router.post('/incomes',response_model=MoneyResponse,status_code=201)
def create_income(data: IncomeInput,actor=Depends(require_permission('finance:write')),repo=Depends(repository)):
    return repo.save_money('income',data,actor)


@router.put('/incomes/{record_id}',response_model=MoneyResponse)
def update_income(record_id: UUID,data: IncomeInput,actor=Depends(require_permission('finance:write')),repo=Depends(repository)):
    return repo.save_money('income',data,actor,str(record_id))
