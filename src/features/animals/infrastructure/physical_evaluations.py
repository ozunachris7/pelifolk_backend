"""Descriptive physical assessments with versioned criterion snapshots, without inferred scores."""
from datetime import date, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import ensure_in_herd, has_exited
from src.core.models import AnimalModel, PhysicalEvaluationModel, AuditModel, UserModel
from src.features.auth.infrastructure.dependencies import require_permission

router = APIRouter(prefix='/physical-evaluations', tags=['Physical evaluations'])
RUBRIC_VERSION = 'descriptive_v1'
CRITERIA = (
    dict(code='body_structure', label='Estructura corporal', description='Describe la forma y proporciones corporales observadas; no deduzcas rendimiento ni valor genético.'),
    dict(code='limbs_hooves', label='Patas y aplomos', description='Describe la posición de las extremidades y el aspecto visible de las pezuñas.'),
    dict(code='movement', label='Desplazamiento', description='Describe cómo se desplaza el animal durante la observación; no sustituye un diagnóstico.'),
    dict(code='coat_features', label='Capa y pelaje', description='Describe color, distribución del pelo y señas físicas visibles; no confirma pureza racial.'),
)


class FindingsInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    body_structure: str | None = Field(default=None, max_length=2000)
    limbs_hooves: str | None = Field(default=None, max_length=2000)
    movement: str | None = Field(default=None, max_length=2000)
    coat_features: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def at_least_one_observation(self):
        if not any(self.model_dump().values()):
            raise ValueError('Record at least one physical criterion')
        return self


class EvaluationInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    animal_id: UUID
    date: date
    evaluated_by: str = Field(min_length=1, max_length=190)
    rubric_version: str = Field(min_length=1, max_length=40)
    findings: FindingsInput
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator('date')
    @classmethod
    def not_future(cls, value):
        if value > date.today():
            raise ValueError('Physical evaluation date cannot be in the future')
        return value


def animal_summary(animal):
    return dict(id=animal.id, name=animal.name, siniiga=animal.siniiga)


def user_name(user):
    return ' '.join(filter(None, [user.name, user.middle_name, user.paternal_lastname, user.maternal_lastname])) if user else 'Usuario no disponible'


class SQLPhysicalRepository:
    def __init__(self, db):
        self.db = db

    def animal(self, animal_id, lock=False):
        statement = select(AnimalModel).where(AnimalModel.id == animal_id)
        animal = self.db.scalar(statement.with_for_update() if lock else statement)
        if animal is None:
            raise ApplicationError('Animal not found', 404)
        return animal

    @staticmethod
    def search(statement, q):
        if q:
            statement = statement.where(or_(AnimalModel.name.icontains(q, autoescape=True), AnimalModel.siniiga.icontains(q, autoescape=True)))
        return statement

    def response(self, row, animal, user):
        return dict(id=row.id, animal=animal_summary(animal), date=row.date, evaluated_by=row.evaluated_by,
                    rubric_version=row.rubric_version, findings=row.findings, notes=row.notes,
                    recorded_by=user_name(user), role_id=row.role_id,
                    created_at=row.created_at.replace(tzinfo=timezone.utc).isoformat())

    def options(self, q, limit):
        statement = self.search(select(AnimalModel).where(~has_exited(AnimalModel.id, date.today())), q)
        return [animal_summary(a) for a in self.db.scalars(statement.order_by(AnimalModel.name, AnimalModel.id).limit(limit))]

    def page(self, q, animal_id, offset, limit):
        statement = self.search(select(PhysicalEvaluationModel, AnimalModel, UserModel).join(
            AnimalModel, AnimalModel.id == PhysicalEvaluationModel.animal_id).outerjoin(UserModel, UserModel.id == PhysicalEvaluationModel.user_id), q)
        if animal_id:
            self.animal(animal_id)
            statement = statement.where(PhysicalEvaluationModel.animal_id == animal_id)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.execute(statement.order_by(PhysicalEvaluationModel.date.desc(), PhysicalEvaluationModel.created_at.desc(), PhysicalEvaluationModel.id).offset(offset).limit(limit))
        return dict(items=[self.response(*r) for r in rows], total=total, offset=offset, limit=limit)

    def create(self, data, actor):
        if data.rubric_version != RUBRIC_VERSION:
            raise ApplicationError('Physical evaluation criteria changed; reload the form', 409)
        animal = self.animal(str(data.animal_id), True)
        if animal.birth_date and data.date < animal.birth_date:
            raise ApplicationError('Physical evaluation date is before birth date', 422)
        ensure_in_herd(self.db, animal.id, data.date)
        observations = data.findings.model_dump()
        findings = [dict(**criterion, observation=observations[criterion['code']] or None) for criterion in CRITERIA]
        row = PhysicalEvaluationModel(animal_id=animal.id, date=data.date, evaluated_by=data.evaluated_by,
            rubric_version=RUBRIC_VERSION, findings=findings, notes=data.notes or None, user_id=actor.id, role_id=actor.role.id)
        self.db.add(row)
        self.db.flush()
        self.db.add(AuditModel(table='physical_evaluations', record_id=row.id, user_id=actor.id, action='INSERT',
            new_values=dict(animal_id=animal.id, date=data.date.isoformat(), evaluated_by=row.evaluated_by,
                            rubric_version=row.rubric_version, findings=findings, notes=row.notes, role_id=actor.role.id)))
        self.db.flush()
        return self.response(row, animal, self.db.get(UserModel, actor.id))


def repository(db: Session = Depends(get_db, scope='function')):
    return SQLPhysicalRepository(db)


@router.get('/criteria')
def criteria(actor=Depends(require_permission('animals:read'))):
    return dict(version=RUBRIC_VERSION, scoring='descriptive', criteria=CRITERIA)


@router.get('/animal-options')
def options(q: str = Query('', max_length=100), limit: int = Query(50, ge=1, le=100),
            actor=Depends(require_permission('animals:read')), repo=Depends(repository)):
    return repo.options(q.strip(), limit)


@router.get('')
def listing(q: str = Query('', max_length=100), animal_id: UUID | None = None,
            offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
            actor=Depends(require_permission('animals:read')), repo=Depends(repository)):
    return repo.page(q.strip(), str(animal_id) if animal_id else None, offset, limit)


@router.post('', status_code=201)
def create(data: EvaluationInput, actor=Depends(require_permission('animals:write')), repo=Depends(repository)):
    return repo.create(data, actor)
