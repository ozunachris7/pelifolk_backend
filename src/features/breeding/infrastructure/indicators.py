"""Read-only reproductive indicators with explicit cohorts, denominators and observation cutoffs."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, aliased
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import effective_exit_query
from src.core.models import AnimalModel, EventModel, EventBirthModel, BirthOffspringModel, EventMatingModel, EventPregnancyModel
from src.features.auth.infrastructure.dependencies import require_permission
from .performance import effective
from .repository import SQLBreedingRepository

router = APIRouter(prefix='/breeding/indicators', tags=['Recorded reproductive indicators'])
Section = Literal['birth_intervals', 'matings', 'offspring']


def filters(date_from: date | None = None, date_to: date | None = None, as_of: date | None = None,
            age_days: int = Query(60, ge=1, le=730)):
    cutoff = as_of or date.today()
    if cutoff > date.today() or date_from and date_from > cutoff or date_to and date_to > cutoff:
        raise ApplicationError('Indicator dates cannot exceed observation cutoff', 422)
    if date_from and date_to and date_from > date_to:
        raise ApplicationError('Invalid report date range', 422)
    return dict(date_from=date_from, date_to=date_to, as_of=cutoff, age_days=age_days)


def included(day, f):
    return day <= f['as_of'] and (not f['date_from'] or day >= f['date_from']) and (not f['date_to'] or day <= f['date_to'])


def decimal_ratio(numerator, denominator, multiplier=1):
    return str((Decimal(numerator) * multiplier / denominator).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if denominator else None


def duration_summary(days):
    return dict(count=len(days), total_days=sum(days), average_days=decimal_ratio(sum(days), len(days)),
                min_days=min(days) if days else None, max_days=max(days) if days else None)


def blank():
    return dict(births=0, birth_intervals=duration_summary([]),
        pregnancy=dict(matings=0, pregnant=0, not_pregnant=0, uncertain=0, no_diagnosis=0,
                       diagnosed=0, percentage=None, unlinked_diagnoses=0, first_positive_delay=duration_summary([])),
        followup=dict(total=0, live_births=0, stillbirths=0, unknown_birth_condition=0,
                      missing_birth_date=0, too_young=0, unobservable=0, without_recorded_death=0,
                      deaths=0, observable=0, percentage=None))


def summarize(rows):
    result = blank()
    intervals, positive = [], []
    for row in rows:
        result['births'] += row['births']
        for section in ('pregnancy', 'followup'):
            for key, value in result[section].items():
                if isinstance(value, int):
                    result[section][key] += row[section][key]
        for target, key in [(intervals, 'birth_intervals'), (positive, 'positive_delays')]:
            source = row['birth_intervals'] if key == 'birth_intervals' else row['pregnancy']['first_positive_delay']
            if source['count']:
                target.append(source)
    for source, destination in [(intervals, result['birth_intervals']), (positive, result['pregnancy']['first_positive_delay'])]:
        destination.update(count=sum(s['count'] for s in source), total_days=sum(s['total_days'] for s in source),
            min_days=min((s['min_days'] for s in source), default=None), max_days=max((s['max_days'] for s in source), default=None))
        destination['average_days'] = decimal_ratio(destination['total_days'], destination['count'])
    result['pregnancy']['percentage'] = decimal_ratio(result['pregnancy']['pregnant'], result['pregnancy']['diagnosed'], 100)
    result['followup']['percentage'] = decimal_ratio(result['followup']['without_recorded_death'], result['followup']['observable'], 100)
    return result


def collect(db, mothers, f):
    ids = [a.id for a in mothers]
    metrics = {a.id:dict(animal=SQLBreedingRepository.summary(a), **blank()) for a in mothers}
    details = {a.id:{'birth_intervals':[], 'matings':[], 'offspring':[]} for a in mothers}
    if not ids:
        return [], details
    cutoff = datetime.combine(f['as_of'], time.max)
    births = defaultdict(list)
    for event in db.scalars(select(EventModel).join(EventBirthModel, EventBirthModel.event_id == EventModel.id).where(
            EventModel.animal_id.in_(ids), EventModel.event_type_id == 7, EventModel.date <= cutoff, effective())
            .order_by(EventModel.date, EventModel.created_at, EventModel.id)):
        births[event.animal_id].append(event)
    for mother_id, events in births.items():
        metrics[mother_id]['births'] = sum(included(e.date.date(), f) for e in events)
        pairs = details[mother_id]['birth_intervals']
        for before, after in zip(events, events[1:]):
            if included(after.date.date(), f):
                pairs.append(dict(previous_birth_id=before.id, previous_date=before.date.date(),
                    birth_event_id=after.id, date=after.date.date(), days=(after.date.date()-before.date.date()).days,
                    predecessor_outside_period=not included(before.date.date(), f)))
        metrics[mother_id]['birth_intervals'] = duration_summary([p['days'] for p in pairs])
    matings = db.execute(select(EventModel, EventMatingModel).join(EventMatingModel, EventMatingModel.event_id == EventModel.id).where(
        EventModel.animal_id.in_(ids), EventModel.event_type_id == 5, EventModel.date <= cutoff, effective())
        .order_by(EventModel.date, EventModel.created_at, EventModel.id)).all()
    by_mating = {event.id:event for event,_ in matings}
    diagnoses = defaultdict(list)
    for event, diagnosis in db.execute(select(EventModel, EventPregnancyModel).join(EventPregnancyModel, EventPregnancyModel.event_id == EventModel.id).where(
            EventModel.animal_id.in_(ids), EventModel.event_type_id == 6, EventModel.date <= cutoff, effective())
            .order_by(EventModel.date, EventModel.created_at, EventModel.id)):
        mating = by_mating.get(diagnosis.mating_event_id)
        if mating and mating.animal_id == event.animal_id and mating.date <= event.date:
            diagnoses[mating.id].append((event, diagnosis))
        elif included(event.date.date(), f):
            metrics[event.animal_id]['pregnancy']['unlinked_diagnoses'] += 1
    for event, mating in matings:
        if not included(event.date.date(), f):
            continue
        history = diagnoses.get(event.id, [])
        latest_event, latest_dx = history[-1] if history else (None, None)
        result = latest_dx.result if latest_dx else 'no_diagnosis'
        first = next((e for e,d in history if d.result == 'pregnant'), None)
        detail = dict(mating_event_id=event.id, date=event.date.date(), result=result,
                      diagnosis_date=latest_event.date.date() if latest_event else None,
                      first_positive_date=first.date.date() if first else None,
                      first_positive_days=(first.date.date()-event.date.date()).days if first else None)
        details[event.animal_id]['matings'].append(detail)
        metric = metrics[event.animal_id]['pregnancy']
        metric['matings'] += 1
        metric[result] += 1
    for mother_id in ids:
        metric = metrics[mother_id]['pregnancy']
        metric['diagnosed'] = metric['pregnant'] + metric['not_pregnant']
        metric['percentage'] = decimal_ratio(metric['pregnant'], metric['diagnosed'], 100)
        metric['first_positive_delay'] = duration_summary([m['first_positive_days'] for m in details[mother_id]['matings'] if m['first_positive_days'] is not None])
    children = db.execute(select(AnimalModel, BirthOffspringModel, EventModel).outerjoin(
        BirthOffspringModel, BirthOffspringModel.animal_id == AnimalModel.id).outerjoin(EventModel, EventModel.id == BirthOffspringModel.event_id)
        .where(AnimalModel.mother_id.in_(ids))).all()
    valid_birth_ids = {e.id for events in births.values() for e in events}
    departures = {}
    child_ids = [c.id for c,_,_ in children]
    if child_ids:
        for event, departure in db.execute(effective_exit_query().where(EventModel.animal_id.in_(child_ids), EventModel.date <= cutoff)
                .order_by(EventModel.date, EventModel.created_at, EventModel.id)):
            departures.setdefault(event.animal_id, (departure.exit_type, event.date.date()))
    for child, link, event in children:
        # Effective birth evidence determines known birth condition. Manual genealogy alone does not.
        known = link is not None and event is not None and event.id in valid_birth_ids and event.animal_id == child.mother_id
        born = event.date.date() if known else child.birth_date
        if born and not included(born, f) or born is None and (f['date_from'] or f['date_to']):
            continue
        metric = metrics[child.mother_id]['followup']
        metric['total'] += 1
        alive = link.alive if known else None
        if alive is True:
            metric['live_births'] += 1
        target = None
        exit_type, exit_date = departures.get(child.id, (None, None))
        if born is None:
            state = 'missing_birth_date'
        elif alive is False:
            state = 'stillbirths'
        elif alive is None:
            state = 'unknown_birth_condition'
        else:
            try:
                target = born + timedelta(days=f['age_days'])
            except OverflowError:
                target = None
            if target is None or target > f['as_of']:
                state = 'too_young'
            elif exit_date and exit_date <= target:
                state = 'deaths' if exit_type in ('death','slaughter') else 'unobservable'
            else:
                state = 'without_recorded_death'
        metric[state] += 1
        details[child.mother_id]['offspring'].append(dict(animal=SQLBreedingRepository.summary(child), birth_date=born,
            born_alive=alive, target_date=target, state=state,
            exit_type=exit_type if exit_date and target and exit_date <= target else None,
            exit_date=exit_date if exit_date and target and exit_date <= target else None))
    for mother_id in ids:
        metric = metrics[mother_id]['followup']
        metric['observable'] = metric['without_recorded_death'] + metric['deaths']
        metric['percentage'] = decimal_ratio(metric['without_recorded_death'], metric['observable'], 100)
        for section in details[mother_id]:
            details[mother_id][section].reverse()
    return [metrics[a.id] for a in mothers], details


def mothers_query(q):
    child, event = aliased(AnimalModel), aliased(EventModel)
    descendants = exists(select(child.id).where(child.mother_id == AnimalModel.id))
    recorded = exists(select(event.id).where(event.animal_id == AnimalModel.id, event.event_type_id.in_([5,6,7]), effective(event)))
    query = select(AnimalModel).where(AnimalModel.sex == 'female', or_(AnimalModel.is_breeder, descendants, recorded))
    if q:
        query = query.where(or_(AnimalModel.name.icontains(q, autoescape=True), AnimalModel.siniiga.icontains(q, autoescape=True)))
    return query.order_by(AnimalModel.name, AnimalModel.id)


@router.get('')
def listing(q: str = Query('', max_length=100), animal_id: UUID | None = None, f=Depends(filters), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
            actor=Depends(require_permission('breeding:read')), db: Session = Depends(get_db, scope='function')):
    query = mothers_query(q.strip())
    if animal_id:
        query = query.where(AnimalModel.id == str(animal_id))
    mothers = db.scalars(query).all()
    rows, _ = collect(db, mothers, f)
    return dict(**f, items=rows[offset:offset+limit], total=len(rows), offset=offset, limit=limit, summary=summarize(rows))


@router.get('/{animal_id}/details')
def detail(animal_id: UUID, section: Section = 'birth_intervals', f=Depends(filters), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
           actor=Depends(require_permission('breeding:read')), db: Session = Depends(get_db, scope='function')):
    mother = SQLBreedingRepository(db).animal(str(animal_id))
    if mother.sex != 'female':
        raise ApplicationError('Reproductive indicators require a female', 422)
    rows, details = collect(db, [mother], f)
    data = details[mother.id][section]
    return dict(**f, parent=rows[0], section=section, items=data[offset:offset+limit], total=len(data), offset=offset, limit=limit)
