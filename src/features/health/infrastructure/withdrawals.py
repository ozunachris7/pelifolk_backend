"""Calendar estimates from actual administrations and saved withdrawal days.

Missing administrations and unreviewed variations never imply clearance.
"""
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, select, or_, func
from sqlalchemy.orm import Session, aliased
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import has_exited
from src.core.models import AnimalModel, EventModel, EventTreatmentModel, ProductModel, TreatmentDoseModel
from src.features.auth.infrastructure.dependencies import require_permission

router = APIRouter(tags=['Health withdrawal'])


def calendar_release(last_day, days):
    """First whole calendar date after the recorded days; never same-day clearance."""
    if days is None or days < 0:
        return None
    try:
        return last_day + timedelta(days=days + 1)
    except (OverflowError, ValueError):
        return None


def treatment_estimate(treatment, day, doses=(), replaced=False):
    last = max(doses, key=lambda d: (d.applied_at_utc, d.id), default=None)
    planned = calendar_release(treatment.end_date - timedelta(days=1), treatment.withdrawal_days)
    estimate = calendar_release(last.clinical_date, treatment.withdrawal_days) if last else None
    reasons = []
    if not last: reasons.append('missing_applications')
    if treatment.withdrawal_days is None: reasons.append('missing_withdrawal_days')
    elif treatment.withdrawal_days < 0: reasons.append('invalid_withdrawal_days')
    if any(d.is_deviation for d in doses): reasons.append('dose_variation')
    if replaced: reasons.append('replaced_treatment')
    if last and treatment.withdrawal_days is not None and treatment.withdrawal_days >= 0 and estimate is None: reasons.append('date_overflow')
    ongoing = treatment.start_date <= day < treatment.end_date
    status = 'unknown' if reasons else ('pending' if ongoing or day < estimate else 'complete')
    applied_at = None
    if last:
        applied_at = last.applied_at_utc.replace(tzinfo=timezone.utc).astimezone(
            timezone(timedelta(minutes=last.utc_offset_minutes))).isoformat()
    return dict(start_date=treatment.start_date, last_day=treatment.end_date - timedelta(days=1),
                withdrawal_days=treatment.withdrawal_days,
                release_date=estimate if not reasons and not ongoing else None,
                estimated_release_date=estimate, planned_release_date=planned,
                last_applied_at=applied_at, application_count=len(doses),
                calculation_basis='applications' if last else 'planned',
                review_reasons=reasons, has_dose_variation='dose_variation' in reasons,
                is_replaced=replaced, status=status, in_treatment=ongoing)


def summaries(db, animal_ids, day, details=False, lock=False):
    result = {key: dict(as_of=day, status='no_records', release_date=None, treatment_count=0,
                       application_count=0, missing_applications_count=0,
                       unknown_count=0, in_treatment=False, items=[]) for key in animal_ids}
    if not animal_ids:
        return result
    replacement = aliased(EventModel)
    replaced = exists(select(replacement.id).where(replacement.replaced_event_id == EventModel.id))
    actual = exists(select(TreatmentDoseModel.id).where(
        TreatmentDoseModel.treatment_event_id == EventModel.id,
        TreatmentDoseModel.product_id == EventTreatmentModel.product_id,
        TreatmentDoseModel.clinical_date <= day))
    statement = select(EventModel, EventTreatmentModel, ProductModel, replaced.label('is_replaced')).join(
        EventTreatmentModel, EventTreatmentModel.event_id == EventModel.id).join(
        ProductModel, ProductModel.id == EventTreatmentModel.product_id).where(
        EventModel.animal_id.in_(animal_ids), or_(EventModel.date <= datetime.combine(day, time.max), actual),
        or_(~replaced, actual))
    doses = {}
    dose_query = select(TreatmentDoseModel).join(EventModel,
        EventModel.id == TreatmentDoseModel.treatment_event_id).where(
            EventModel.animal_id.in_(animal_ids), TreatmentDoseModel.clinical_date <= day)
    if lock:
        dose_query = dose_query.with_for_update()
        statement = statement.with_for_update()
    for dose in db.scalars(dose_query):
        doses.setdefault((dose.treatment_event_id, dose.product_id), []).append(dose)
    for event, treatment, product, is_replaced in db.execute(statement.order_by(EventModel.date.desc(), EventModel.id, ProductModel.id)):
        summary = result[event.animal_id]
        records = doses.get((event.id, treatment.product_id), [])
        estimate = treatment_estimate(treatment, day, records, bool(is_replaced))
        summary['treatment_count'] += 1
        summary['application_count'] += len(records)
        summary['missing_applications_count'] += int(not records)
        summary['unknown_count'] += int(estimate['status'] == 'unknown')
        summary['in_treatment'] |= estimate['in_treatment']
        release = estimate['release_date']
        if release is not None and (summary['release_date'] is None or release > summary['release_date']):
            summary['release_date'] = release
        if details:
            summary['items'].append(dict(event_id=event.id, product_id=product.id, product_name=product.name, **estimate))
    for summary in result.values():
        if summary['unknown_count']:
            summary['status'] = 'unknown'
        elif summary['treatment_count']:
            summary['status'] = 'pending' if summary['in_treatment'] or day < summary['release_date'] else 'complete'
        # An incomplete or ongoing record must not expose an animal-level clearance date.
        if summary['unknown_count'] or summary['in_treatment']:
            summary['release_date'] = None
        if not details:
            del summary['items']
    return result


def animal_summary(db, animal_id, day, details=False, lock=False):
    animal = db.get(AnimalModel, animal_id)
    if animal is None:
        raise ApplicationError('Animal not found', 404)
    return dict(animal=dict(id=animal.id, name=animal.name, siniiga=animal.siniiga),
                **summaries(db, [animal_id], day, details, lock)[animal_id])


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
