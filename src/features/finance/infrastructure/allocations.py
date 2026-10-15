from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.models import AnimalModel, AnimalGroupModel, AuditModel, ExpenseModel, ExpenseAllocationModel, ExpenseCategoryModel, HealthCaseModel, FeedingModel
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.feeding.infrastructure.repository import SQLFeedingRepository
from src.features.finance.domain.allocations import AllocationsInput, TargetKind
from .routes import date_range

router = APIRouter(prefix='/finance', tags=['Finance'])
MODELS = {'animal': AnimalModel, 'group': AnimalGroupModel, 'health_case': HealthCaseModel}
COLUMNS = {'animal': 'animal_id', 'group': 'group_id', 'health_case': 'health_case_id'}


def allocation_key(row):
    for kind, column in COLUMNS.items():
        if getattr(row, column) is not None: return kind, getattr(row, column)
    raise ApplicationError('Allocation target is missing', 409)


def money(amount, rows):
    """Largest remainders distribute cents deterministically without inflating the expense."""
    cents = amount * 100
    raw = [cents * r.percentage / 100 for r in rows]
    total_percentage = sum((r.percentage for r in rows), Decimal('0'))
    if total_percentage > 100: raise ApplicationError('Expense allocations exceed 100 percent', 409)
    target = int((cents * total_percentage / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    base = [int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in raw]
    order = sorted(range(len(rows)), key=lambda n: (-(raw[n] - base[n]), allocation_key(rows[n]), rows[n].id))
    for n in order[:target - sum(base)]: base[n] += 1
    return [Decimal(value) / 100 for value in base]


def target(db, kind, target_id):
    row = db.get(MODELS[kind], target_id)
    if row is None: raise ApplicationError('Allocation target not found', 422)
    if kind == 'health_case':
        animal = db.get(AnimalModel, row.animal_id)
        return dict(id=row.id, name=f'Caso {row.start_date.isoformat()} · {animal.name or animal.siniiga or animal.id}', siniiga=animal.siniiga)
    return dict(id=row.id, name=row.name, siniiga=row.siniiga if kind == 'animal' else None)


def allocation_response(db, expense):
    rows = db.scalars(select(ExpenseAllocationModel).where(ExpenseAllocationModel.expense_id == expense.id).order_by(ExpenseAllocationModel.id)).all()
    values = money(expense.amount, rows)
    items = [dict(id=r.id, kind=allocation_key(r)[0], target=target(db, *allocation_key(r)), percentage=str(r.percentage), amount=f'{value:.2f}') for r, value in zip(rows, values)]
    assigned = sum(values, Decimal('0.00'))
    return dict(expense=dict(id=expense.id, amount=f'{expense.amount:.2f}', date=expense.date, description=expense.description),
        allocations=items, assigned_amount=f'{assigned:.2f}', unassigned_amount=f'{expense.amount-assigned:.2f}')


def expense_row(db, expense_id, lock=False):
    query = select(ExpenseModel).where(ExpenseModel.id == expense_id)
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None: raise ApplicationError('Expense not found', 404)
    return row


@router.get('/allocation-options')
def options(kind: TargetKind = 'animal', q: str = Query('', max_length=100), actor=Depends(require_permission('finance:read')), db: Session=Depends(get_db, scope='function')):
    model = MODELS[kind]
    query = select(model)
    if kind == 'health_case':
        query = query.join(AnimalModel, AnimalModel.id == HealthCaseModel.animal_id)
        if q.strip(): query = query.where(or_(AnimalModel.name.icontains(q.strip(), autoescape=True), AnimalModel.siniiga.icontains(q.strip(), autoescape=True)))
        query = query.order_by(HealthCaseModel.start_date.desc(), HealthCaseModel.id)
    else:
        if q.strip():
            tests = [model.name.icontains(q.strip(), autoescape=True)]
            if kind == 'animal': tests.append(model.siniiga.icontains(q.strip(), autoescape=True))
            query = query.where(or_(*tests))
        query = query.order_by(model.name, model.id)
    return [target(db, kind, r.id) for r in db.scalars(query.limit(100))]


@router.get('/expenses/{expense_id}/allocations')
def get_allocations(expense_id: UUID, actor=Depends(require_permission('finance:read')), db: Session=Depends(get_db, scope='function')):
    return allocation_response(db, expense_row(db, str(expense_id)))


@router.put('/expenses/{expense_id}/allocations')
def save_allocations(expense_id: UUID, data: AllocationsInput, actor=Depends(require_permission('finance:write')), db: Session=Depends(get_db, scope='function')):
    expense = expense_row(db, str(expense_id), True)
    before = allocation_response(db, expense)
    for allocation in data.allocations: target(db, allocation.kind, str(allocation.target_id))
    db.execute(delete(ExpenseAllocationModel).where(ExpenseAllocationModel.expense_id == expense.id))
    for allocation in data.allocations:
        db.add(ExpenseAllocationModel(expense_id=expense.id, percentage=allocation.percentage, **{COLUMNS[allocation.kind]: str(allocation.target_id)}))
    db.flush()
    after = allocation_response(db, expense)
    db.add(AuditModel(user_id=actor.id, table='expense_allocations', record_id=expense.id,
        action='UPDATE' if before['allocations'] else 'INSERT', old_values=jsonable_encoder(before), new_values=jsonable_encoder(after)))
    return after


@router.get('/costs')
def costs(kind: Literal['animal', 'group'], target_id: UUID, dates=Depends(date_range),
          offset: int=Query(0, ge=0), limit: int=Query(25, ge=1, le=100), actor=Depends(require_permission('finance:read')), db: Session=Depends(get_db, scope='function')):
    target_info = target(db, kind, str(target_id)); date_from, date_to = dates
    query = select(ExpenseModel, ExpenseCategoryModel).join(ExpenseCategoryModel, ExpenseCategoryModel.id == ExpenseModel.expense_category_id)
    if date_from: query = query.where(ExpenseModel.date >= date_from)
    if date_to: query = query.where(ExpenseModel.date <= date_to)
    # Select only relevant expenses, then load ALL their shares before rounding.
    matching = select(ExpenseAllocationModel.expense_id)
    if kind == 'animal':
        cases = select(HealthCaseModel.id).where(HealthCaseModel.animal_id == str(target_id))
        matching = matching.where(or_(ExpenseAllocationModel.animal_id == str(target_id), ExpenseAllocationModel.health_case_id.in_(cases)))
    else: matching = matching.where(ExpenseAllocationModel.group_id == str(target_id))
    query = query.where(ExpenseModel.id.in_(matching))
    records = db.execute(query.order_by(ExpenseModel.date.desc(), ExpenseModel.id)).all()
    case_ids = set(db.scalars(select(HealthCaseModel.id).where(HealthCaseModel.animal_id == str(target_id)))) if kind == 'animal' else set()
    items = []; total = Decimal('0.00')
    for expense, category in records:
        shares = db.scalars(select(ExpenseAllocationModel).where(ExpenseAllocationModel.expense_id == expense.id).order_by(ExpenseAllocationModel.id)).all()
        for row, amount in zip(shares, money(expense.amount, shares)):
            row_kind, row_target = allocation_key(row)
            if (row_kind == kind and row_target == str(target_id)) or (row_kind == 'health_case' and row_target in case_ids):
                items.append(dict(expense_id=expense.id, allocation_id=row.id, date=expense.date, category=dict(id=category.id, name=category.name),
                    description=expense.description, expense_amount=f'{expense.amount:.2f}', percentage=str(row.percentage), amount=f'{amount:.2f}', via=row_kind))
                total += amount
    feeding = None
    if 'feeding:read' in actor.role.permissions:
        repo = SQLFeedingRepository(db)
        feeding_query = select(FeedingModel.quantity, repo.price_expression()).where((FeedingModel.animal_id if kind == 'animal' else FeedingModel.group_id) == str(target_id))
        if date_from: feeding_query = feeding_query.where(FeedingModel.date >= date_from)
        if date_to: feeding_query = feeding_query.where(FeedingModel.date <= date_to)
        feed_count = unpriced = 0; feed_cost = Decimal('0.00')
        for quantity, price in db.execute(feeding_query):
            feed_count += 1
            if price is None: unpriced += 1
            else: feed_cost += (quantity * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        feeding = dict(total=feed_count, unpriced_count=unpriced, total_cost=f'{feed_cost:.2f}')
    from datetime import date
    return dict(as_of=date.today(), kind=kind, target=target_info, date_from=date_from, date_to=date_to,
        items=items[offset:offset+limit], total=len(items), assigned_expenses=f'{total:.2f}', feeding=feeding, offset=offset, limit=limit)
