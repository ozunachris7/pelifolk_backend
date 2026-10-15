from datetime import date, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import ensure_in_herd
from src.core.models import AnimalModel, AnimalDecisionModel, AuditModel, UserModel
from src.features.auth.infrastructure.dependencies import require_permission

DecisionKind = Literal['retain_breeding','exclude_breeding','separate','sale_planned','purchase_reason','other']


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    date: date
    kind: DecisionKind
    reason: str = Field(min_length=1, max_length=5000)

    @field_validator('date')
    @classmethod
    def not_future(cls, value):
        if value > date.today():
            raise ValueError('Decision date cannot be in the future')
        return value


class DecisionResponse(DecisionInput):
    id: str
    animal_id: str
    recorded_by: str
    role_id: str
    created_at: str


class DecisionPage(BaseModel):
    items: list[DecisionResponse]
    total: int
    offset: int
    limit: int


class SQLDecisionRepository:
    def __init__(self, db):
        self.db = db

    def animal(self, animal_id, lock=False):
        statement = select(AnimalModel).where(AnimalModel.id == animal_id)
        animal = self.db.scalar(statement.with_for_update() if lock else statement)
        if animal is None:
            raise ApplicationError('Animal not found', 404)
        return animal

    @staticmethod
    def response(row, user):
        return dict(id=row.id, animal_id=row.animal_id, date=row.date, kind=row.kind,
            reason=row.reason, role_id=row.role_id,
            recorded_by=' '.join(filter(None,[user.name,user.middle_name,user.paternal_lastname,user.maternal_lastname])) if user else 'Usuario no disponible',
            created_at=row.created_at.replace(tzinfo=timezone.utc).isoformat())

    def page(self, animal_id, kind, offset, limit):
        self.animal(animal_id)
        statement = select(AnimalDecisionModel, UserModel).outerjoin(
            UserModel, UserModel.id == AnimalDecisionModel.user_id).where(AnimalDecisionModel.animal_id == animal_id)
        if kind:
            statement = statement.where(AnimalDecisionModel.kind == kind)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.execute(statement.order_by(AnimalDecisionModel.date.desc(),
            AnimalDecisionModel.created_at.desc(), AnimalDecisionModel.id.desc()).offset(offset).limit(limit))
        return dict(items=[self.response(*row) for row in rows], total=total, offset=offset, limit=limit)

    def create(self, animal_id, data, actor):
        animal = self.animal(animal_id, True)
        if animal.birth_date and data.date < animal.birth_date:
            raise ApplicationError('Decision date is before birth date', 422)
        ensure_in_herd(self.db, animal.id, data.date)
        row = AnimalDecisionModel(animal_id=animal.id, user_id=actor.id, role_id=actor.role.id,
                                  **data.model_dump(mode='python'))
        self.db.add(row);self.db.flush()
        self.db.add(AuditModel(table='animal_decisions', record_id=row.id, user_id=actor.id,
            action='INSERT', new_values=dict(animal_id=animal.id, role_id=actor.role.id,
                                            **data.model_dump(mode='json'))))
        self.db.flush()
        return self.response(row, self.db.get(UserModel,actor.id))


router = APIRouter(prefix='/animals', tags=['Animal decisions'])


def repository(db: Session = Depends(get_db, scope='function')):
    return SQLDecisionRepository(db)


@router.get('/{animal_id}/decisions', response_model=DecisionPage)
def listing(animal_id: UUID, kind: DecisionKind | None = None,
            offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
            actor=Depends(require_permission('animals:read')), repo=Depends(repository)):
    return repo.page(str(animal_id),kind,offset,limit)


@router.post('/{animal_id}/decisions', response_model=DecisionResponse, status_code=201)
def create(animal_id: UUID, data: DecisionInput, actor=Depends(require_permission('animals:write')),
           repo=Depends(repository)):
    return repo.create(str(animal_id),data,actor)
