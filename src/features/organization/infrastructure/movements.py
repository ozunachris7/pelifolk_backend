from datetime import date, datetime, time
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import has_exited
from src.core.locations import effective_location_query, latest_location_event_id, location_summary
from src.core.models import AnimalModel, AuditModel, EventModel, LocationModel, UserModel
from src.features.auth.infrastructure.dependencies import require_permission

router = APIRouter(prefix='/locations', tags=['Location movements'])


class MovementInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    animal_id: UUID
    location_id: UUID
    date: date
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('date')
    @classmethod
    def past(cls, value):
        if value > date.today(): raise ValueError('Movement date cannot be in the future')
        return value


def positions_query():
    return select(AnimalModel, EventModel, LocationModel, has_exited(AnimalModel.id, date.today()).label('exited')).select_from(AnimalModel).outerjoin(
        EventModel, EventModel.id == latest_location_event_id()).outerjoin(LocationModel, LocationModel.id == EventModel.location_id)


def position(row):
    a, event, location, exited = row
    known = location_summary(location, event)
    return dict(animal=dict(id=a.id, name=a.name, siniiga=a.siniiga), exited=bool(exited),
        current_location=known if not exited else None, last_known_location=known)


@router.get('/animal-positions')
def positions(q: str=Query('', max_length=100), status: Literal['active', 'exited', 'all']='active',
              location_id: UUID | None=None, offset: int=Query(0, ge=0), limit: int=Query(25, ge=1, le=100),
              actor=Depends(require_permission('locations:read')), db: Session=Depends(get_db, scope='function')):
    query = positions_query()
    if status != 'all': query = query.where(has_exited(AnimalModel.id, date.today()) if status == 'exited' else ~has_exited(AnimalModel.id, date.today()))
    if q.strip(): query = query.where(or_(AnimalModel.name.icontains(q.strip(), autoescape=True), AnimalModel.siniiga.icontains(q.strip(), autoescape=True)))
    if location_id: query = query.where(LocationModel.id == str(location_id))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return dict(as_of=date.today(), items=[position(row) for row in db.execute(query.order_by(AnimalModel.name, AnimalModel.id).offset(offset).limit(limit))], total=total, offset=offset, limit=limit)


@router.get('/animals/{animal_id}/history')
def history(animal_id: UUID, offset: int=Query(0, ge=0), limit: int=Query(25, ge=1, le=100),
            actor=Depends(require_permission('locations:read')), db: Session=Depends(get_db, scope='function')):
    current = db.execute(positions_query().where(AnimalModel.id == str(animal_id))).first()
    if current is None: raise ApplicationError('Animal not found', 404)
    query = effective_location_query().add_columns(LocationModel, UserModel).select_from(EventModel).join(LocationModel, LocationModel.id == EventModel.location_id).join(UserModel, UserModel.id == EventModel.user_id)
    rows = db.execute(query.where(EventModel.animal_id == str(animal_id), EventModel.date <= datetime.combine(date.today(), time.max)).order_by(EventModel.date, EventModel.created_at, EventModel.id)).all()
    items = []; previous = None
    for event, location, user in rows:
        destination = location_summary(location, event)
        items.append(dict(id=event.id, date=event.date.date(), from_location=previous, to_location=destination, reason=event.reason,
            event_type_id=event.event_type_id, recorded_by=' '.join(filter(None, [user.name, user.middle_name, user.paternal_lastname, user.maternal_lastname]))))
        previous = destination
    items.reverse()
    return dict(as_of=date.today(), **position(current), items=items[offset:offset+limit], total=len(items), offset=offset, limit=limit)


@router.post('/movements', status_code=201)
def move(data: MovementInput, actor=Depends(require_permission('locations:write')), db: Session=Depends(get_db, scope='function')):
    # Location before animal is consistent with catalog deactivation checks.
    location = db.scalar(select(LocationModel).where(LocationModel.id == str(data.location_id)).with_for_update())
    if location is None: raise ApplicationError('Location not found', 404)
    if not location.active: raise ApplicationError('Location is inactive', 409)
    animal = db.scalar(select(AnimalModel).where(AnimalModel.id == str(data.animal_id)).with_for_update())
    if animal is None: raise ApplicationError('Animal not found', 404)
    if db.scalar(select(AnimalModel.id).where(AnimalModel.id == animal.id, has_exited(AnimalModel.id, date.today()))): raise ApplicationError('Animal already has an exit', 409)
    if animal.birth_date and data.date < animal.birth_date: raise ApplicationError('Movement date cannot precede birth', 422)
    latest = db.scalar(effective_location_query().where(EventModel.animal_id == animal.id).order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id.desc()).limit(1).with_for_update())
    if latest and data.date <= latest.date.date(): raise ApplicationError('Movement date must be after the last location record', 409)
    if latest and latest.location_id == location.id: raise ApplicationError('Animal is already at this location', 409)
    event = EventModel(animal_id=animal.id, event_type_id=9, date=datetime.combine(data.date, time.min), user_id=actor.id, role_id=actor.role.id, location_id=location.id, reason=data.reason)
    db.add(event); db.flush()
    db.add(AuditModel(user_id=actor.id, table='events', record_id=event.id, action='INSERT', new_values=jsonable_encoder(dict(
        animal_id=animal.id, event_type_id=9, date=data.date, location_id=location.id, from_location_id=latest.location_id if latest else None, reason=data.reason, role_id=actor.role.id))))
    return dict(id=event.id, animal=dict(id=animal.id, name=animal.name, siniiga=animal.siniiga), location=location_summary(location, event), date=data.date, reason=data.reason)
