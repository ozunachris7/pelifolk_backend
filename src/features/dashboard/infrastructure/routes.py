from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, exists
from sqlalchemy.orm import Session, aliased
from src.core.database import get_db
from src.core.herd import has_exited
from src.core.models import (AnimalModel, EventModel, HealthCaseModel, HealthProgramModel,
    ProductModel, EventPregnancyModel, IncomeModel, ExpenseModel, EventMatingModel, EventBirthModel, FeedingModel, FeedModel, UnitModel)
from src.features.auth.infrastructure.dependencies import current_user, require_permission
from src.features.finance.infrastructure.repository import SQLFinanceRepository
from src.features.feeding.infrastructure.repository import SQLFeedingRepository
from src.features.health.infrastructure.program_repository import SQLProgramRepository

router = APIRouter(prefix='/dashboard', tags=['Dashboard'])


@router.get('/finance-trend')
def finance_trend(date_from: date | None = None, date_to: date | None = None,
                  actor=Depends(require_permission('finance:read')),
                  db: Session=Depends(get_db, scope='function')):
    today = date.today()
    finish = date_to or today
    # Include the current month and the preceding five by default.
    month_index = max(12, finish.year * 12 + finish.month - 1 - 5)
    start = date_from or date(month_index // 12, month_index % 12 + 1, 1)
    month_count = (finish.year - start.year) * 12 + finish.month - start.month + 1
    if start > finish or finish > today or month_count > 24:
        raise HTTPException(422, 'Choose an ordered period of at most 24 months, ending no later than today')

    months = {}
    for index in range(month_count):
        absolute = start.year * 12 + start.month - 1 + index
        month = date(absolute // 12, absolute % 12 + 1, 1).isoformat()[:7]
        months[month] = dict(month=month, income_total=Decimal('0.00'),
                             expense_total=Decimal('0.00'), income_count=0, expense_count=0)
    # Aggregate the full date range in SQL, independently from paginated movement lists.
    for model, prefix in ((IncomeModel, 'income'), (ExpenseModel, 'expense')):
        year = func.extract('year', model.date)
        month = func.extract('month', model.date)
        rows = db.execute(select(year, month, func.sum(model.amount), func.count()).where(
            model.date >= start, model.date <= finish).group_by(year, month))
        for y, m, amount, count in rows:
            bucket = months[f'{int(y):04d}-{int(m):02d}']
            bucket[f'{prefix}_total'] = amount
            bucket[f'{prefix}_count'] = count

    items = []
    for bucket in months.values():
        items.append({**bucket,
            'income_total': format(bucket['income_total'], '.2f'),
            'expense_total': format(bucket['expense_total'], '.2f'),
            'balance': format(bucket['income_total'] - bucket['expense_total'], '.2f')})
    return dict(as_of=today, date_from=start, date_to=finish, currency='MXN', items=items,
                income_total=format(sum((b['income_total'] for b in months.values()), Decimal('0.00')), '.2f'),
                expense_total=format(sum((b['expense_total'] for b in months.values()), Decimal('0.00')), '.2f'),
                movement_count=sum(b['income_count'] + b['expense_count'] for b in months.values()))


@router.get('/breeding-trend')
def breeding_trend(date_from: date | None = None, date_to: date | None = None,
                   actor=Depends(require_permission('breeding:read')),
                   db: Session=Depends(get_db, scope='function')):
    today = date.today()
    finish = date_to or today
    month_index = max(12, finish.year * 12 + finish.month - 1 - 5)
    start = date_from or date(month_index // 12, month_index % 12 + 1, 1)
    month_count = (finish.year - start.year) * 12 + finish.month - start.month + 1
    if start > finish or finish > today or month_count > 24:
        raise HTTPException(422, 'Choose an ordered period of at most 24 months, ending no later than today')
    months = {}
    for index in range(month_count):
        absolute = start.year * 12 + start.month - 1 + index
        month = date(absolute // 12, absolute % 12 + 1, 1).isoformat()[:7]
        months[month] = dict(month=month, matings=0, births=0)
    replacement = aliased(EventModel)
    effective = ~exists(select(replacement.id).where(replacement.replaced_event_id == EventModel.id))
    year = func.extract('year', EventModel.date)
    month = func.extract('month', EventModel.date)
    for model, event_type, key in ((EventMatingModel, 5, 'matings'), (EventBirthModel, 7, 'births')):
        # Count effective typed events, never offspring rows or a paginated event list.
        rows = db.execute(select(year, month, func.count()).select_from(EventModel)
            .join(model, model.event_id == EventModel.id).where(
                EventModel.event_type_id == event_type, effective,
                EventModel.date >= datetime.combine(start, time.min),
                EventModel.date <= datetime.combine(finish, time.max)).group_by(year, month))
        for y, m, count in rows:
            months[f'{int(y):04d}-{int(m):02d}'][key] = count
    items = list(months.values())
    matings = sum(item['matings'] for item in items)
    births = sum(item['births'] for item in items)
    return dict(as_of=today, date_from=start, date_to=finish, items=items,
                matings_total=matings, births_total=births, event_count=matings + births)


@router.get('/health-trend')
def health_trend(date_from: date | None = None, date_to: date | None = None,
                   actor=Depends(require_permission('health:read')),
                   db: Session=Depends(get_db, scope='function')):
    today = date.today()
    finish = date_to or today
    month_index = max(12, finish.year * 12 + finish.month - 1 - 5)
    start = date_from or date(month_index // 12, month_index % 12 + 1, 1)
    month_count = (finish.year - start.year) * 12 + finish.month - start.month + 1
    if start > finish or finish > today or month_count > 24:
        raise HTTPException(422, 'Choose an ordered period of at most 24 months, ending no later than today')
    months = {}
    for index in range(month_count):
        absolute = start.year * 12 + start.month - 1 + index
        month = date(absolute // 12, absolute % 12 + 1, 1).isoformat()[:7]
        months[month] = dict(month=month, started=0, closed=0)
    # Count one start per case and only its current, saved closure. Reopened cases have no closure.
    for column, key, closed_only in ((HealthCaseModel.start_date, 'started', False),
                                     (HealthCaseModel.closed_date, 'closed', True)):
        year = func.extract('year', column)
        month = func.extract('month', column)
        query = select(year, month, func.count()).where(column >= start, column <= finish)
        if closed_only:
            query = query.where(HealthCaseModel.status == 'closed')
        for y, m, count in db.execute(query.group_by(year, month)):
            months[f'{int(y):04d}-{int(m):02d}'][key] = count
    items = list(months.values())
    started = sum(item['started'] for item in items)
    closed = sum(item['closed'] for item in items)
    return dict(as_of=today, date_from=start, date_to=finish, items=items,
                started_total=started, closed_total=closed, event_count=started + closed)


@router.get('/feeding-trend')
def feeding_trend(date_from: date | None = None, date_to: date | None = None,
                  actor=Depends(require_permission('feeding:read')),
                  db: Session=Depends(get_db, scope='function')):
    today = date.today()
    finish = date_to or today
    month_index = max(12, finish.year * 12 + finish.month - 1 - 5)
    start = date_from or date(month_index // 12, month_index % 12 + 1, 1)
    month_count = (finish.year - start.year) * 12 + finish.month - start.month + 1
    if start > finish or finish > today or month_count > 24:
        raise HTTPException(422, 'Choose an ordered period of at most 24 months, ending no later than today')
    months = {}
    for index in range(month_count):
        absolute = start.year * 12 + start.month - 1 + index
        month = date(absolute // 12, absolute % 12 + 1, 1).isoformat()[:7]
        months[month] = dict(month=month, total_cost=Decimal('0.00'),
                             consumption_count=0, unpriced_count=0, quantities={})
    price = SQLFeedingRepository.price_expression()
    rows = db.execute(select(FeedingModel.date, FeedingModel.quantity, UnitModel.code, price)
        .join(FeedModel, FeedModel.id == FeedingModel.feed_id)
        .join(UnitModel, UnitModel.id == FeedModel.unit_id)
        .where(FeedingModel.date >= start, FeedingModel.date <= finish))
    quantities = {}
    for day, quantity, code, unit_cost in rows:
        bucket = months[day.isoformat()[:7]]
        bucket['consumption_count'] += 1
        bucket['quantities'][code] = bucket['quantities'].get(code, Decimal('0.00')) + quantity
        quantities[code] = quantities.get(code, Decimal('0.00')) + quantity
        if unit_cost is None:
            bucket['unpriced_count'] += 1
        else:
            # Match feeding reports: use each consumption's historical price and round per row.
            bucket['total_cost'] += (quantity * unit_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    def units(values):
        return [dict(unit_code=code, quantity=format(values[code], '.2f')) for code in sorted(values)]
    items = [{**b, 'total_cost': format(b['total_cost'], '.2f'),
              'quantities': units(b['quantities'])} for b in months.values()]
    return dict(as_of=today, date_from=start, date_to=finish, items=items,
                total_cost=format(sum((b['total_cost'] for b in months.values()), Decimal('0.00')), '.2f'),
                consumption_count=sum(b['consumption_count'] for b in months.values()),
                unpriced_count=sum(b['unpriced_count'] for b in months.values()), quantities=units(quantities))


@router.get('/summary')
def summary(actor=Depends(current_user), db: Session=Depends(get_db, scope='function')):
    today = date.today()
    start = today.replace(day=1)
    end = datetime.combine(today, time.max)
    permissions = actor.role.permissions
    result = dict(as_of=today, period_from=start, period_to=today, herd=None,
                  health=None, breeding=None, finance=None, feeding=None, activity=[])
    replacement = aliased(EventModel)
    effective = ~exists(select(replacement.id).where(replacement.replaced_event_id == EventModel.id))
    event_types = []
    if 'animals:read' in permissions:
        active = ~has_exited(AnimalModel.id, today)
        total = db.scalar(select(func.count()).select_from(AnimalModel))
        counts = dict(db.execute(select(AnimalModel.sex, func.count()).where(active).group_by(AnimalModel.sex)).all())
        active_count = sum(counts.values())
        result['herd'] = dict(total=total, active=active_count, exited=total-active_count,
                              female=counts.get('female', 0), male=counts.get('male', 0))
    if 'health:read' in permissions:
        cases = dict(db.execute(select(HealthCaseModel.status, func.count())
                                .group_by(HealthCaseModel.status)).all())
        pending = []
        attention_count = 0
        repo = SQLProgramRepository(db)
        programs = db.scalars(select(HealthProgramModel).join(ProductModel,
            ProductModel.id == HealthProgramModel.product_id).where(HealthProgramModel.active == True,
            ProductModel.active == True).order_by(HealthProgramModel.name, HealthProgramModel.id))
        for program in programs:
            schedule = repo.schedule(program.id, '', 'attention', 0, 5)
            attention_count += schedule['total']
            for item in schedule['items']:
                pending.append(dict(program_id=program.id, program_name=program.name,
                    animal=item['animal'], due_date=item['due_date'], status=item['status']))
        rank = {'overdue':0, 'due':1, 'upcoming':2, 'missing_birth_date':3}
        pending.sort(key=lambda p:(rank[p['status']], p['due_date'] or date.max, p['program_name'], p['animal']['id']))
        result['health'] = dict(open_cases=cases.get('open',0), treatment_cases=cases.get('under_treatment',0),
                                closed_cases=cases.get('closed',0), total_cases=sum(cases.values()),
                                attention_count=attention_count, pending=pending[:5])
        event_types.extend([1,2,3])
    if 'breeding:read' in permissions:
        latest = set()
        pregnant = 0
        events = db.execute(select(EventModel, EventPregnancyModel.result).outerjoin(
            EventPregnancyModel, EventPregnancyModel.event_id == EventModel.id).where(
            effective, EventModel.event_type_id.in_([6,7]), EventModel.date <= end,
            ~has_exited(EventModel.animal_id,today)).order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id.desc()))
        for event, diagnosis in events:
            if event.animal_id not in latest:
                latest.add(event.animal_id)
                if event.event_type_id == 6 and diagnosis == 'pregnant':
                    pregnant += 1
        births = db.scalar(select(func.count()).select_from(EventModel).where(effective,
            EventModel.event_type_id == 7, EventModel.date >= datetime.combine(start,time.min), EventModel.date <= end))
        result['breeding'] = dict(pregnant=pregnant, births=births)
        event_types.extend([5,6,7])
    if 'finance:read' in permissions:
        result['finance'] = SQLFinanceRepository(db).summary(start,today)
    if 'feeding:read' in permissions:
        page = SQLFeedingRepository(db).page('',None,None,start,today,0,1)
        result['feeding'] = dict(consumptions=page['total'], cost=str(page['total_cost']), unpriced_count=page['unpriced_count'])
    if 'locations:read' in permissions:
        event_types.append(9)
    if 'weights:read' in permissions:
        event_types.append(4)
    if 'exits:read' in permissions:
        event_types.append(8)
    if event_types:
        records = db.execute(select(EventModel, AnimalModel).join(AnimalModel, AnimalModel.id == EventModel.animal_id).where(
            effective, EventModel.event_type_id.in_(event_types), EventModel.date <= end).order_by(
            EventModel.date.desc(),EventModel.created_at.desc(),EventModel.id.desc()).limit(8))
        result['activity'] = [dict(id=e.id, type_id=e.event_type_id, date=e.date,
            animal_name=a.name, siniiga=a.siniiga) for e,a in records]
    return result
