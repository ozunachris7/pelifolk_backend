"""Latest recorded management plans, with permission-scoped current context."""
from datetime import date, datetime, time
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.herd import has_exited
from src.core.models import AnimalModel, AnimalDecisionModel, UserModel, EventModel, EventMatingModel, EventBirthModel, EventPregnancyModel
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.breeding.infrastructure.performance import effective, exit_states
from src.features.health.infrastructure.withdrawals import summaries as withdrawal_summaries
from src.features.breeding.infrastructure.offspring_health import collect_case_counts
from .decisions import SQLDecisionRepository

ManagementKind = Literal['retain_breeding','exclude_breeding','separate','sale_planned']
MANAGEMENT_KINDS = ('retain_breeding','exclude_breeding','separate','sale_planned')
router = APIRouter(prefix='/management-decisions', tags=['Current recorded management decisions'])


def current_query():
    # Rank before filtering by kind: filtering first could resurrect a superseded sale plan.
    ranked = select(AnimalDecisionModel.id.label('decision_id'), func.row_number().over(
        partition_by=AnimalDecisionModel.animal_id,
        order_by=(AnimalDecisionModel.date.desc(), AnimalDecisionModel.created_at.desc(), AnimalDecisionModel.id.desc())).label('position')).where(
            AnimalDecisionModel.kind.in_(MANAGEMENT_KINDS), AnimalDecisionModel.date <= date.today()).subquery()
    return select(AnimalDecisionModel, AnimalModel, UserModel).join(
        ranked, (ranked.c.decision_id == AnimalDecisionModel.id) & (ranked.c.position == 1)).join(
        AnimalModel, AnimalModel.id == AnimalDecisionModel.animal_id).outerjoin(UserModel, UserModel.id == AnimalDecisionModel.user_id)


def breeding_context(db, ids):
    result = {key:dict(last_mating_date=None, last_birth_date=None, pregnancy=None) for key in ids}
    if not ids:
        return result
    cutoff = datetime.combine(date.today(), time.max)
    matings = select(EventModel, EventMatingModel).join(EventMatingModel, EventMatingModel.event_id == EventModel.id).where(
        or_(EventModel.animal_id.in_(ids), EventMatingModel.male_id.in_(ids)), EventModel.date <= cutoff, effective())
    for event, mating in db.execute(matings.order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id.desc())):
        for key in {event.animal_id, mating.male_id} & result.keys():
            if result[key]['last_mating_date'] is None:
                result[key]['last_mating_date'] = event.date.date()
    # The latest birth or pregnancy diagnosis determines whether a diagnosis remains after the last birth.
    events = select(EventModel, EventPregnancyModel).outerjoin(EventPregnancyModel, EventPregnancyModel.event_id == EventModel.id).where(
        EventModel.animal_id.in_(ids), EventModel.event_type_id.in_([6,7]), EventModel.date <= cutoff, effective())
    found_latest = set()
    for event, diagnosis in db.execute(events.order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id.desc())):
        context = result[event.animal_id]
        if event.event_type_id == 7 and context['last_birth_date'] is None:
            context['last_birth_date'] = event.date.date()
        if event.animal_id not in found_latest:
            found_latest.add(event.animal_id)
            if event.event_type_id == 6 and diagnosis:
                context['pregnancy'] = dict(result=diagnosis.result, date=event.date.date())
    return result


@router.get('')
def listing(q: str = Query('', max_length=100), kind: ManagementKind | None = None,
            status: Literal['active','exited','all'] = 'active', sex: Literal['female','male'] | None = None,
            offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
            actor=Depends(require_permission('animals:read')), db: Session = Depends(get_db, scope='function')):
    query = current_query()
    if q.strip():
        query = query.where(or_(AnimalModel.name.icontains(q.strip(), autoescape=True), AnimalModel.siniiga.icontains(q.strip(), autoescape=True)))
    if kind:
        query = query.where(AnimalDecisionModel.kind == kind)
    if sex:
        query = query.where(AnimalModel.sex == sex)
    if status != 'all':
        query = query.where(~has_exited(AnimalModel.id, date.today()) if status == 'active' else has_exited(AnimalModel.id, date.today()))
    filtered = query.subquery()
    total = db.scalar(select(func.count()).select_from(filtered))
    summary = {key:0 for key in MANAGEMENT_KINDS}
    for key, count in db.execute(select(filtered.c.kind, func.count()).group_by(filtered.c.kind)):
        summary[key] = count
    records = db.execute(query.order_by(AnimalDecisionModel.date.desc(), AnimalDecisionModel.created_at.desc(), AnimalDecisionModel.id.desc())
                         .offset(offset).limit(limit)).all()
    ids = [animal.id for _,animal,_ in records]
    states = exit_states(db, ids)
    permissions = actor.role.permissions
    health = collect_case_counts(db, ids) if 'health:read' in permissions else {}
    withdrawals = withdrawal_summaries(db, ids, date.today()) if 'health:read' in permissions else {}
    breeding = breeding_context(db, ids) if 'breeding:read' in permissions else {}
    items = []
    for decision, animal, user in records:
        state, exit_date = states.get(animal.id, ('active', None))
        item = dict(animal=dict(id=animal.id, name=animal.name, siniiga=animal.siniiga, sex=animal.sex, is_breeder=animal.is_breeder),
                    status=state, exit_date=exit_date, decision=SQLDecisionRepository.response(decision, user))
        if 'health:read' in permissions:
            item.update(health=health[animal.id], withdrawal=withdrawals[animal.id])
        if 'breeding:read' in permissions:
            item['breeding'] = breeding[animal.id]
        items.append(item)
    return dict(as_of=date.today(), items=items, total=total, summary=summary, offset=offset, limit=limit)
