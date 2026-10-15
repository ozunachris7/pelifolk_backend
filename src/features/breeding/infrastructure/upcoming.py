"""Birth estimates derived from the latest effective diagnosis/birth, never saved as events."""
from datetime import date, datetime, time, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.herd import has_exited
from src.core.models import AnimalModel, EventModel, EventMatingModel, EventPregnancyModel
from src.features.auth.infrastructure.dependencies import require_permission
from .repository import SQLBreedingRepository

router = APIRouter(prefix='/breeding', tags=['Breeding'])
GESTATION_DAYS = 147
Status = Literal['all', 'past_estimate', 'due', 'upcoming', 'scheduled', 'missing_mating']


@router.get('/upcoming-births')
def upcoming_births(q: str = Query('', max_length=100), status: Status = 'all',
                    notice_days: int = Query(14, ge=1, le=60), offset: int = Query(0, ge=0),
                    limit: int = Query(25, ge=1, le=100), actor=Depends(require_permission('breeding:read')),
                    db: Session = Depends(get_db, scope='function')):
    today = date.today(); end = datetime.combine(today, time.max)
    repo = SQLBreedingRepository(db)
    query = repo.query().join(AnimalModel, AnimalModel.id == EventModel.animal_id).where(
        EventModel.event_type_id.in_([6, 7]), EventModel.date <= end,
        AnimalModel.sex == 'female', ~has_exited(AnimalModel.id, today))
    if q.strip():
        query = query.where(or_(AnimalModel.name.icontains(q.strip(), autoescape=True),
                                AnimalModel.siniiga.icontains(q.strip(), autoescape=True)))
    events = db.scalars(query.order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id.desc())).all()
    latest = {}; last_birth = {}
    for event in events:
        latest.setdefault(event.animal_id, event)
        if event.event_type_id == 7: last_birth.setdefault(event.animal_id, event)
    ids = [e.id for e in latest.values() if e.event_type_id == 6]
    diagnoses = {d.event_id: d for d in db.scalars(select(EventPregnancyModel).where(EventPregnancyModel.event_id.in_(ids)))} if ids else {}
    mating_ids = [d.mating_event_id for d in diagnoses.values() if d.result == 'pregnant' and d.mating_event_id]
    matings = {e.id: (e, m) for e, m in db.execute(repo.query().with_only_columns(EventModel, EventMatingModel).join(
        EventMatingModel, EventMatingModel.event_id == EventModel.id).where(EventModel.id.in_(mating_ids), EventModel.event_type_id == 5))} if mating_ids else {}
    rows = []
    for animal_id, event in latest.items():
        diagnosis = diagnoses.get(event.id)
        if event.event_type_id != 6 or not diagnosis or diagnosis.result != 'pregnant': continue
        mating = matings.get(diagnosis.mating_event_id)
        reason = 'unlinked' if not diagnosis.mating_event_id else 'unavailable_mating'
        if mating and (mating[0].animal_id != animal_id or mating[0].date > event.date):
            mating = None; reason = 'invalid_mating'
        birth = last_birth.get(animal_id)
        if mating and birth and (mating[0].date, mating[0].created_at, mating[0].id) <= (birth.date, birth.created_at, birth.id):
            mating = None; reason = 'before_last_birth'
        expected = mating[0].date.date() + timedelta(days=GESTATION_DAYS) if mating else None
        remaining = (expected - today).days if expected else None
        state = 'missing_mating' if remaining is None else 'past_estimate' if remaining < 0 else 'due' if remaining == 0 else 'upcoming' if remaining <= notice_days else 'scheduled'
        if status != 'all' and state != status: continue
        rows.append(dict(id=event.id, animal=repo.summary(repo.animal(animal_id)), diagnosis_date=event.date.date(),
                         mating_event_id=diagnosis.mating_event_id, mating_date=mating[0].date.date() if mating else None,
                         male=repo.summary(repo.animal(mating[1].male_id)) if mating else None,
                         expected_birth_date=expected, days_remaining=remaining, status=state,
                         missing_reason=reason if not mating else None))
    rows.sort(key=lambda r: (r['expected_birth_date'] is None, r['expected_birth_date'] or date.max,
                             (r['animal']['name'] or r['animal']['siniiga'] or '').casefold(), r['animal']['id']))
    counts = {key: sum(r['status'] == key for r in rows) for key in ['past_estimate', 'due', 'upcoming', 'scheduled', 'missing_mating']}
    return dict(as_of=today, gestation_days=GESTATION_DAYS, notice_days=notice_days, items=rows[offset:offset+limit],
                total=len(rows), counts=counts, offset=offset, limit=limit)
