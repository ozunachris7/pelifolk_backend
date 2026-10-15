"""Calendar estimate, based on recorded treatment duration and labeled days.

end_date is exclusive. For positive withdrawal periods, allow full calendar
 days after last_day; the estimate never certifies food safety.
"""
from datetime import date, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, select, or_, func
from sqlalchemy.orm import Session, aliased
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import has_exited
from src.core.models import AnimalModel, EventModel, EventTreatmentModel, ProductModel
from src.features.auth.infrastructure.dependencies import require_permission

router = APIRouter(tags=['Health withdrawal'])


def treatment_estimate(treatment, day):
    days = treatment.withdrawal_days
    release = None
    if days is not None:
        try:
            release = treatment.end_date + timedelta(days=days)
        except OverflowError:
            pass
    status = 'unknown' if release is None else ('pending' if day < release else 'complete')
    return dict(start_date=treatment.start_date, last_day=treatment.end_date - timedelta(days=1),
                withdrawal_days=days, release_date=release, status=status,
                in_treatment=day < treatment.end_date)


def summaries(db, animal_ids, day, details=False):
    result = {key: dict(as_of=day, status='no_records', release_date=None, treatment_count=0,
                       unknown_count=0, in_treatment=False, items=[]) for key in animal_ids}
    if not animal_ids:
        return result
    replacement = aliased(EventModel)
    statement = select(EventModel, EventTreatmentModel, ProductModel).join(
        EventTreatmentModel, EventTreatmentModel.event_id == EventModel.id).join(
        ProductModel, ProductModel.id == EventTreatmentModel.product_id).where(
        EventModel.animal_id.in_(animal_ids), EventModel.date <= datetime.combine(day, time.max),
        ~exists(select(replacement.id).where(replacement.replaced_event_id == EventModel.id)))
    for event, treatment, product in db.execute(statement.order_by(EventModel.date.desc(), EventModel.id)):
        summary = result[event.animal_id]
        estimate = treatment_estimate(treatment, day)
        summary['treatment_count'] += 1
        summary['unknown_count'] += int(estimate['status'] == 'unknown')
        summary['in_treatment'] |= estimate['in_treatment']
        release = estimate['release_date']
        if release is not None and (summary['release_date'] is None or release > summary['release_date']):
            summary['release_date'] = release
        if details:
            summary['items'].append(dict(event_id=event.id, product_name=product.name, **estimate))
    for summary in result.values():
        if summary['unknown_count']:
            summary['status'] = 'unknown'
        elif summary['treatment_count']:
            summary['status'] = 'pending' if day < summary['release_date'] else 'complete'
        if not details:
            del summary['items']
    return result


def animal_summary(db, animal_id, day, details=False):
    animal = db.get(AnimalModel, animal_id)
    if animal is None:
        raise ApplicationError('Animal not found', 404)
    return dict(animal=dict(id=animal.id, name=animal.name, siniiga=animal.siniiga),
                **summaries(db, [animal_id], day, details)[animal_id])


@router.get('/health/withdrawals')
def listing(q: str = Query('', max_length=100), offset: int = Query(0, ge=0),
            limit: int = Query(25, ge=1, le=100),
            actor=Depends(require_permission('health:read')),
            db: Session = Depends(get_db, scope='function')):
    # Paginate the herd in SQL; only fetch treatment rows for this page.
    statement = select(AnimalModel).where(~has_exited(AnimalModel.id, date.today()))
    if q.strip():
        statement = statement.where(or_(AnimalModel.name.icontains(q.strip(), autoescape=True),
                                       AnimalModel.siniiga.icontains(q.strip(), autoescape=True)))
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    animals = list(db.scalars(statement.order_by(AnimalModel.name, AnimalModel.id).offset(offset).limit(limit)))
    values = summaries(db, [a.id for a in animals], date.today())
    return dict(items=[dict(animal=dict(id=a.id, name=a.name, siniiga=a.siniiga), **values[a.id]) for a in animals],
                total=total, offset=offset, limit=limit)


@router.get('/health/animals/{animal_id}/withdrawal')
def detail(animal_id: UUID, actor=Depends(require_permission('health:read')),
           db: Session = Depends(get_db, scope='function')):
    return animal_summary(db, str(animal_id), date.today(), True)


@router.get('/exits/animals/{animal_id}/withdrawal')
def departure_check(animal_id: UUID, date: date,
                    actor=Depends(require_permission('exits:read')),
                    db: Session = Depends(get_db, scope='function')):
    return animal_summary(db, str(animal_id), date)
