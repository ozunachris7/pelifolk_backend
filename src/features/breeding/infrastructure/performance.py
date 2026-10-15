"""Recorded reproductive outcomes; no genetic scoring or inferred survival."""
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, aliased
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import effective_exit_query
from src.core.models import AnimalModel, BirthOffspringModel, EventBirthModel, EventMatingModel, EventModel, EventWeaningModel, EventWeightModel
from src.features.auth.infrastructure.dependencies import require_permission
from .repository import SQLBreedingRepository

router = APIRouter(prefix='/breeding/performance', tags=['Breeding'])


def period(date_from: date | None = None, date_to: date | None = None):
    if date_from and date_to and date_from > date_to:
        raise ApplicationError('Invalid report date range', 422)
    return dict(date_from=date_from, date_to=date_to)


def effective(event=EventModel):
    replacement = aliased(EventModel)
    return ~exists(select(replacement.id).where(replacement.replaced_event_id == event.id))


def event_period(query, f):
    query = query.where(EventModel.date <= datetime.combine(date.today(), time.max), effective())
    if f['date_from']: query = query.where(EventModel.date >= datetime.combine(f['date_from'], time.min))
    if f['date_to']: query = query.where(EventModel.date <= datetime.combine(f['date_to'], time.max))
    return query


def exit_states(db, ids):
    states = {}
    if ids:
        for event, departure in db.execute(effective_exit_query().where(
            EventModel.animal_id.in_(ids), EventModel.date <= datetime.combine(date.today(), time.max))
            .order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id.desc())):
            states.setdefault(event.animal_id, (departure.exit_type, event.date.date()))
    return states


def collect(db, parents, f):
    ids = [a.id for a in parents]
    if not ids: return [], {}
    sex = parents[0].sex
    column = AnimalModel.mother_id if sex == 'female' else AnimalModel.father_id
    children_query = select(AnimalModel, BirthOffspringModel, EventModel).outerjoin(
        BirthOffspringModel, BirthOffspringModel.animal_id == AnimalModel.id).outerjoin(
        EventModel, EventModel.id == BirthOffspringModel.event_id).where(column.in_(ids),
            or_(AnimalModel.birth_date.is_(None), AnimalModel.birth_date <= date.today()))
    if f['date_from']: children_query = children_query.where(AnimalModel.birth_date >= f['date_from'])
    if f['date_to']: children_query = children_query.where(AnimalModel.birth_date <= f['date_to'])
    children = db.execute(children_query.order_by(AnimalModel.birth_date.desc(), AnimalModel.name, AnimalModel.id)).all()
    child_ids = [a.id for a, _, _ in children]
    weanings = {}
    if child_ids:
        query = select(EventWeaningModel, EventModel, EventWeightModel).join(
            EventModel, EventModel.id == EventWeaningModel.event_id).join(
            EventWeightModel, EventWeightModel.event_id == EventWeaningModel.event_id).where(
                EventWeaningModel.animal_id.in_(child_ids), EventModel.event_type_id == 4,
                EventModel.date <= datetime.combine(date.today(), time.max), effective())
        for marker, event, measurement in db.execute(query):
            weanings[marker.animal_id] = dict(date=event.date.date(), weight_kg=str(measurement.weight_kg),
                age_days=(event.date.date() - marker.birth_date_snapshot).days if marker.birth_date_snapshot else None)
    states = exit_states(db, ids + [a.id for a, _, _ in children])
    linked_ids = [e.id for _, _, e in children if e]
    valid_births = set(db.scalars(select(EventModel.id).where(EventModel.id.in_(linked_ids), EventModel.event_type_id == 7,
        EventModel.date <= datetime.combine(date.today(), time.max), effective()))) if linked_ids else set()
    metrics = {a.id: dict(animal=SQLBreedingRepository.summary(a), is_breeder=a.is_breeder,
        status=states.get(a.id, ('active', None))[0], matings=0, births=0, offspring=0,
        live_births=0, stillbirths=0, unknown_birth_condition=0, post_birth_deaths=0,
        in_herd=0, other_exits=0, weighed_offspring=0, average_birth_weight_kg=None,
        offspring_per_recorded_birth=None, weaned_offspring=0, average_weaning_weight_kg=None) for a in parents}
    detail = {a.id: [] for a in parents}; weights = {a.id: [] for a in parents}; birth_sets = {a.id: set() for a in parents}
    weaning_weights = {a.id: [] for a in parents}
    for child, link, event in children:
        parent_id = child.mother_id if sex == 'female' else child.father_id
        m = metrics[parent_id]; state, exit_day = states.get(child.id, ('active', None))
        known = link is not None and event is not None and event.id in valid_births
        alive = link.alive if known else None
        weight = link.birth_weight_kg if known else None
        m['offspring'] += 1
        m['live_births' if alive is True else 'stillbirths' if alive is False else 'unknown_birth_condition'] += 1
        if alive is True and state in ('death', 'slaughter'): m['post_birth_deaths'] += 1
        if state == 'active': m['in_herd'] += 1
        elif state not in ('death', 'slaughter'): m['other_exits'] += 1
        if weight is not None: weights[parent_id].append(weight)
        weaning = weanings.get(child.id)
        if weaning is not None: weaning_weights[parent_id].append(Decimal(weaning['weight_kg']))
        if known: birth_sets[parent_id].add(event.id)
        detail[parent_id].append(dict(animal=SQLBreedingRepository.summary(child), birth_date=child.birth_date,
            born_alive=alive, birth_weight_kg=str(weight) if weight is not None else None,
            birth_event_id=event.id if known else None, status=state, exit_date=exit_day, weaning=weaning))
    mating_query = select(EventModel, EventMatingModel).join(EventMatingModel, EventMatingModel.event_id == EventModel.id).where(
        (EventModel.animal_id if sex == 'female' else EventMatingModel.male_id).in_(ids), EventModel.event_type_id == 5)
    for event, mating in db.execute(event_period(mating_query, f)):
        metrics[event.animal_id if sex == 'female' else mating.male_id]['matings'] += 1
    if sex == 'female':
        births = event_period(select(EventModel, BirthOffspringModel).join(EventBirthModel, EventBirthModel.event_id == EventModel.id)
            .outerjoin(BirthOffspringModel, BirthOffspringModel.event_id == EventModel.id).where(EventModel.animal_id.in_(ids), EventModel.event_type_id == 7), f)
        birth_sets = {a.id: set() for a in parents}
        pups = {a.id: 0 for a in parents}
        for event, child in db.execute(births):
            birth_sets[event.animal_id].add(event.id)
            if child: pups[event.animal_id] += 1
        for a in parents:
            n = len(birth_sets[a.id]); metrics[a.id]['births'] = n
            metrics[a.id]['offspring_per_recorded_birth'] = str((Decimal(pups[a.id]) / n).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if n else None
    else:
        for a in parents: metrics[a.id]['births'] = len(birth_sets[a.id])
    for a in parents:
        values = weights[a.id]; metrics[a.id]['weighed_offspring'] = len(values)
        metrics[a.id]['average_birth_weight_kg'] = str((sum(values) / len(values)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if values else None
        values = weaning_weights[a.id]
        metrics[a.id]['weaned_offspring'] = len(values)
        metrics[a.id]['average_weaning_weight_kg'] = str((sum(values) / len(values)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if values else None
    return [metrics[a.id] for a in parents], detail


@router.get('')
def performance(sex: Literal['female', 'male'] = 'female', q: str = Query('', max_length=100),
                status: Literal['all', 'active', 'exited'] = 'all', f=Depends(period),
                offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
                actor=Depends(require_permission('breeding:read')), db: Session = Depends(get_db, scope='function')):
    child = aliased(AnimalModel); event = aliased(EventModel)
    has_children = exists(select(child.id).where((child.mother_id if sex == 'female' else child.father_id) == AnimalModel.id))
    if sex == 'female':
        recorded = exists(select(event.id).where(event.animal_id == AnimalModel.id, event.event_type_id.in_([5, 6, 7]), event.date <= datetime.combine(date.today(), time.max), effective(event)))
    else:
        recorded = exists(select(EventMatingModel.event_id).join(EventModel, EventModel.id == EventMatingModel.event_id).where(EventMatingModel.male_id == AnimalModel.id, EventModel.date <= datetime.combine(date.today(), time.max), effective()))
    query = select(AnimalModel).where(AnimalModel.sex == sex, or_(AnimalModel.is_breeder, has_children, recorded))
    if q.strip(): query = query.where(or_(AnimalModel.name.icontains(q.strip(), autoescape=True), AnimalModel.siniiga.icontains(q.strip(), autoescape=True)))
    parents = db.scalars(query.order_by(AnimalModel.name, AnimalModel.id)).all()
    rows, _ = collect(db, parents, f)
    if status != 'all': rows = [r for r in rows if (r['status'] == 'active') == (status == 'active')]
    summary = {key: sum(r[key] for r in rows) for key in ['matings', 'births', 'offspring', 'live_births', 'stillbirths', 'unknown_birth_condition', 'post_birth_deaths', 'in_herd', 'other_exits', 'weaned_offspring']}
    return dict(as_of=date.today(), sex=sex, **f, items=rows[offset:offset+limit], total=len(rows), summary=summary, offset=offset, limit=limit)


@router.get('/{animal_id}/offspring')
def offspring(animal_id: UUID, f=Depends(period), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
              actor=Depends(require_permission('breeding:read')), db: Session = Depends(get_db, scope='function')):
    animal = SQLBreedingRepository(db).animal(str(animal_id))
    metrics, children = collect(db, [animal], f)
    rows = children[animal.id]
    return dict(as_of=date.today(), **f, parent=metrics[0], items=rows[offset:offset+limit], total=len(rows), offset=offset, limit=limit)
