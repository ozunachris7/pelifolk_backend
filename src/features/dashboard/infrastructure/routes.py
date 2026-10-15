from datetime import date, datetime, time
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, exists
from sqlalchemy.orm import Session, aliased
from src.core.database import get_db
from src.core.herd import has_exited
from src.core.models import (AnimalModel, EventModel, HealthCaseModel, HealthProgramModel,
    ProductModel, EventPregnancyModel)
from src.features.auth.infrastructure.dependencies import current_user
from src.features.finance.infrastructure.repository import SQLFinanceRepository
from src.features.feeding.infrastructure.repository import SQLFeedingRepository
from src.features.health.infrastructure.program_repository import SQLProgramRepository

router = APIRouter(prefix='/dashboard', tags=['Dashboard'])


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
        cases = dict(db.execute(select(HealthCaseModel.status, func.count()).where(
            HealthCaseModel.status != 'closed').group_by(HealthCaseModel.status)).all())
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
