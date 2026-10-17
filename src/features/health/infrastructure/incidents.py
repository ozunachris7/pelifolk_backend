"""Structured incident reports and an append-only record of their follow-up."""
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import ensure_in_herd
from src.core.models import AnimalIncidentModel, IncidentFollowupModel, AnimalModel, HealthCaseModel, UserModel, AuditModel
from src.features.auth.infrastructure.dependencies import require_permission
from .repository import SQLHealthRepository

router = APIRouter(prefix='/health/incidents', tags=['Animal incidents'])
Kind = Literal['accident', 'abortion', 'attack', 'poisoning', 'disappearance', 'other']
Status = Literal['open', 'in_progress', 'closed']


class DatedInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    date: date

    @field_validator('date')
    @classmethod
    def not_future(cls, value):
        if value > date.today():
            raise ValueError('Incident date cannot be in the future')
        return value


class IncidentInput(DatedInput):
    animal_id: UUID
    kind: Kind
    description: str = Field(min_length=1, max_length=5000)
    location: str | None = Field(default=None, max_length=190)
    initial_actions: str | None = Field(default=None, max_length=5000)
    health_case_id: UUID | None = None


class FollowupInput(DatedInput):
    expected_version: int = Field(ge=0)
    status: Status
    notes: str = Field(min_length=1, max_length=5000)
    health_case_id: UUID | None = None


class SQLIncidentRepository(SQLHealthRepository):
    def linked_case(self, case_id, animal_id, lock=False):
        if not case_id:
            return None
        statement = select(HealthCaseModel).where(HealthCaseModel.id == str(case_id))
        case = self.db.scalar(statement.with_for_update() if lock else statement)
        if case is None:
            raise ApplicationError('Incident case not found', 422)
        if case.animal_id != animal_id:
            raise ApplicationError('Incident case belongs to another animal', 422)
        return case

    @staticmethod
    def case_summary(case):
        return dict(id=case.id, reason=case.reason, status=case.status, start_date=case.start_date) if case else None

    def response(self, row):
        return dict(id=row.id, animal=self.summary(self.animal(row.animal_id)), date=row.date,
                    kind=row.kind, description=row.description, location=row.location,
                    initial_actions=row.initial_actions, status=row.status, version=row.version,
                    health_case=self.case_summary(self.db.get(HealthCaseModel, row.health_case_id)) if row.health_case_id else None,
                    recorded_by=self.user_name(self.db.get(UserModel, row.user_id)))

    def followup_response(self, row):
        return dict(id=row.id, date=row.date, notes=row.notes, status=row.status, version=row.version,
                    health_case=self.case_summary(self.db.get(HealthCaseModel, row.health_case_id)) if row.health_case_id else None,
                    recorded_by=self.user_name(self.db.get(UserModel, row.user_id)))

    def incident(self, incident_id, lock=False):
        statement = select(AnimalIncidentModel).where(AnimalIncidentModel.id == incident_id)
        row = self.db.scalar(statement.with_for_update() if lock else statement)
        if row is None:
            raise ApplicationError('Incident not found', 404)
        return row

    def page(self, q, animal_id, kind, status, offset, limit):
        statement = self.search(select(AnimalIncidentModel).join(AnimalModel, AnimalModel.id == AnimalIncidentModel.animal_id), q)
        if animal_id:
            self.animal(animal_id)
            statement = statement.where(AnimalIncidentModel.animal_id == animal_id)
        if kind:
            statement = statement.where(AnimalIncidentModel.kind == kind)
        if status:
            statement = statement.where(AnimalIncidentModel.status == status)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.scalars(statement.order_by(AnimalIncidentModel.date.desc(), AnimalIncidentModel.created_at.desc(), AnimalIncidentModel.id).offset(offset).limit(limit))
        return dict(items=[self.response(r) for r in rows], total=total, offset=offset, limit=limit)

    def detail(self, incident_id, offset, limit, lock=False):
        row = self.incident(incident_id, lock)
        statement = select(IncidentFollowupModel).where(IncidentFollowupModel.incident_id == row.id)
        ordered = statement.order_by(IncidentFollowupModel.version.desc())
        # Versions are consecutive and entries cannot be removed; this is the count.
        total = row.version
        paged = ordered.offset(offset).limit(limit)
        rows = self.db.scalars(paged.with_for_update() if lock else paged).all()
        last_query = ordered.limit(1)
        last = self.db.scalar(last_query.with_for_update() if lock else last_query)
        return dict(incident=self.response(row), last_followup_date=last.date if last else None,
                    followups=dict(items=[self.followup_response(r) for r in rows], total=total, offset=offset, limit=limit))

    def create(self, data, actor):
        animal = self.animal(str(data.animal_id), True)
        if animal.birth_date and data.date < animal.birth_date:
            raise ApplicationError('Incident date is before birth date', 422)
        ensure_in_herd(self.db, animal.id, data.date)
        if data.kind == 'abortion' and animal.sex != 'female':
            raise ApplicationError('Abortion incident requires a female', 422)
        case = self.linked_case(data.health_case_id, animal.id, True)
        row = AnimalIncidentModel(animal_id=animal.id, date=data.date, kind=data.kind,
            description=data.description, location=data.location or None, initial_actions=data.initial_actions or None,
            health_case_id=case.id if case else None, status='open', version=0, user_id=actor.id, role_id=actor.role.id)
        self.db.add(row)
        self.db.flush()
        self.db.add(AuditModel(table='animal_incidents', record_id=row.id, user_id=actor.id, action='INSERT',
            new_values={**data.model_dump(mode='json'), 'status':'open', 'version':0, 'role_id':actor.role.id}))
        self.db.flush()
        return self.response(row)

    def add_followup(self, incident_id, data, actor):
        reference = self.incident(incident_id)
        self.animal(reference.animal_id, True)
        self.db.expire(reference)
        row = self.incident(incident_id, True)
        if row.version != data.expected_version:
            raise ApplicationError('Incident changed; reload before updating', 409)
        # A current locking read is necessary after waiting for the animal lock in MySQL.
        last = self.db.scalar(select(IncidentFollowupModel).where(IncidentFollowupModel.incident_id == row.id)
                              .order_by(IncidentFollowupModel.version.desc()).limit(1).with_for_update())
        if data.date < (last.date if last else row.date):
            raise ApplicationError('Follow-up date is before incident history', 422)
        case = self.linked_case(data.health_case_id, row.animal_id, True)
        previous = row.status
        row.version += 1
        row.status = data.status
        entry = IncidentFollowupModel(incident_id=row.id, date=data.date, notes=data.notes,
            status=data.status, version=row.version, health_case_id=case.id if case else None, user_id=actor.id, role_id=actor.role.id)
        self.db.add(entry)
        self.db.flush()
        self.db.add(AuditModel(table='incident_followups', record_id=entry.id, user_id=actor.id, action='INSERT',
            new_values={**data.model_dump(mode='json'), 'incident_id':row.id, 'animal_id':row.animal_id,
                        'version':row.version, 'previous_status':previous, 'role_id':actor.role.id}))
        self.db.add(AuditModel(table='animal_incidents', record_id=row.id, user_id=actor.id, action='UPDATE',
            old_values={'status':previous, 'version':data.expected_version},
            new_values={'status':row.status, 'version':row.version, 'followup_id':entry.id, 'role_id':actor.role.id}))
        self.db.flush()
        return self.detail(row.id, 0, 25, lock=True)

    def case_options(self, animal_id, q, limit):
        self.animal(animal_id)
        statement = select(HealthCaseModel).where(HealthCaseModel.animal_id == animal_id)
        if q:
            statement = statement.where(HealthCaseModel.reason.icontains(q, autoescape=True))
        return [self.case_summary(c) for c in self.db.scalars(statement.order_by(HealthCaseModel.start_date.desc(), HealthCaseModel.id).limit(limit))]


def repository(db: Session = Depends(get_db, scope='function')):
    return SQLIncidentRepository(db)


@router.get('')
def listing(q: str = Query('', max_length=100), animal_id: UUID | None = None, kind: Kind | None = None,
            status: Status | None = None, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
            actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.page(q.strip(), str(animal_id) if animal_id else None, kind, status, offset, limit)


@router.get('/case-options')
def case_options(animal_id: UUID, q: str = Query('', max_length=100), limit: int = Query(50, ge=1, le=100),
                 actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.case_options(str(animal_id), q.strip(), limit)


@router.get('/{incident_id}')
def detail(incident_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
           actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.detail(str(incident_id), offset, limit)


@router.post('', status_code=201)
def create(data: IncidentInput, actor=Depends(require_permission('health:incidents:write')), repo=Depends(repository)):
    return repo.create(data, actor)


@router.post('/{incident_id}/followups', status_code=201)
def followup(incident_id: UUID, data: FollowupInput, actor=Depends(require_permission('health:incidents:write')), repo=Depends(repository)):
    return repo.add_followup(str(incident_id), data, actor)
