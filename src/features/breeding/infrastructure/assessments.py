"""Descriptive maternal and individual offspring assessments tied to recorded births."""
from datetime import date, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, aliased
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import ensure_in_herd
from src.core.models import AnimalModel, EventModel, EventBirthModel, BirthOffspringModel, BreedingAssessmentModel, UserModel, AuditModel
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.animals.infrastructure.physical_evaluations import animal_summary, user_name

router = APIRouter(prefix='/breeding/assessments', tags=['Maternal and offspring assessments'])
Kind = Literal['maternal', 'offspring']
VERSION = 'breeding_descriptive_v1'
CRITERIA = {
    'maternal': (
        dict(code='acceptance', label='Aceptación de las crías', description='Describe el acercamiento, aceptación o rechazo observado hacia las crías de este parto.'),
        dict(code='nursing', label='Amamantamiento observado', description='Describe los intentos de mamar y la respuesta de la madre; no deduzcas cantidad o calidad de leche.'),
        dict(code='care', label='Cuidado y atención', description='Describe conductas observadas de atención, contacto o cuidado hacia las crías.'),
    ),
    'offspring': (
        dict(code='body_features', label='Características físicas de la cría', description='Describe rasgos visibles de esta cría; no atribuyas herencia genética ni pureza racial.'),
        dict(code='movement', label='Desplazamiento observado', description='Describe postura y desplazamiento observados; no sustituye un diagnóstico.'),
        dict(code='development', label='Desarrollo observado', description='Describe cambios o conductas observados. Pesos y crecimiento medido se registran en Manejo.'),
    ),
}


class AssessmentInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    birth_event_id: UUID
    kind: Kind
    offspring_id: UUID | None = None
    date: date
    evaluated_by: str = Field(min_length=1, max_length=190)
    rubric_version: str = Field(min_length=1, max_length=40)
    findings: dict[str, str | None] = Field(min_length=1, max_length=3)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator('date')
    @classmethod
    def not_future(cls, value):
        if value > date.today():
            raise ValueError('Assessment date cannot be in the future')
        return value

    @model_validator(mode='after')
    def valid_findings_and_target(self):
        if (self.kind == 'offspring') != (self.offspring_id is not None):
            raise ValueError('Select offspring only for an offspring assessment')
        allowed = {c['code'] for c in CRITERIA[self.kind]}
        if set(self.findings) - allowed:
            raise ValueError('Unknown assessment criteria')
        self.findings = {k: (v.strip() or None) if v is not None else None for k,v in self.findings.items()}
        if not any(self.findings.values()) or any(len(v) > 2000 for v in self.findings.values() if v):
            raise ValueError('Describe at least one criterion with up to 2000 characters')
        return self


class SQLAssessmentRepository:
    def __init__(self, db):
        self.db = db

    def animal(self, key):
        row = self.db.get(AnimalModel, key)
        if row is None:
            raise ApplicationError('Animal not found', 404)
        return row

    @staticmethod
    def effective_births():
        replacement = aliased(EventModel)
        return select(EventModel).join(EventBirthModel, EventBirthModel.event_id == EventModel.id).where(
            ~exists(select(replacement.id).where(replacement.replaced_event_id == EventModel.id)))

    def birth_response(self, event):
        children = self.db.execute(select(BirthOffspringModel, AnimalModel).join(AnimalModel, AnimalModel.id == BirthOffspringModel.animal_id)
                                  .where(BirthOffspringModel.event_id == event.id).order_by(AnimalModel.name, AnimalModel.id))
        return dict(id=event.id, date=event.date.date(), mother=animal_summary(self.animal(event.animal_id)),
                    offspring=[dict(animal=animal_summary(a), alive_at_birth=c.alive) for c,a in children])

    def birth_options(self, q, offset, limit):
        statement = self.effective_births().join(AnimalModel, AnimalModel.id == EventModel.animal_id).where(func.date(EventModel.date) <= date.today())
        if q:
            statement = statement.where(or_(AnimalModel.name.icontains(q, autoescape=True), AnimalModel.siniiga.icontains(q, autoescape=True)))
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.scalars(statement.order_by(EventModel.date.desc(), EventModel.id).offset(offset).limit(limit))
        return dict(items=[self.birth_response(e) for e in rows], total=total, offset=offset, limit=limit)

    def response(self, row):
        event = self.db.get(EventModel, row.birth_event_id)
        replaced = bool(self.db.scalar(select(EventModel.id).where(EventModel.replaced_event_id == event.id).limit(1)))
        return dict(id=row.id, kind=row.kind, animal=animal_summary(self.animal(row.animal_id)),
                    mother=animal_summary(self.animal(row.mother_id)), father=animal_summary(self.animal(row.father_id)) if row.father_id else None,
                    birth_event_id=row.birth_event_id, birth_date=event.date.date(), birth_replaced=replaced,
                    date=row.date, evaluated_by=row.evaluated_by, rubric_version=row.rubric_version, findings=row.findings,
                    notes=row.notes, recorded_by=user_name(self.db.get(UserModel, row.user_id)), role_id=row.role_id,
                    created_at=row.created_at.replace(tzinfo=timezone.utc).isoformat())

    def page(self, q, kind, animal_id, birth_event_id, offset, limit):
        subject = aliased(AnimalModel)
        mother = aliased(AnimalModel)
        statement = select(BreedingAssessmentModel).join(subject, subject.id == BreedingAssessmentModel.animal_id).join(mother, mother.id == BreedingAssessmentModel.mother_id)
        if q:
            statement = statement.where(or_(subject.name.icontains(q,autoescape=True), subject.siniiga.icontains(q,autoescape=True), mother.name.icontains(q,autoescape=True), mother.siniiga.icontains(q,autoescape=True)))
        if kind:
            statement = statement.where(BreedingAssessmentModel.kind == kind)
        if animal_id:
            self.animal(animal_id)
            statement = statement.where(or_(BreedingAssessmentModel.animal_id == animal_id, BreedingAssessmentModel.mother_id == animal_id, BreedingAssessmentModel.father_id == animal_id))
        if birth_event_id:
            statement = statement.where(BreedingAssessmentModel.birth_event_id == birth_event_id)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.scalars(statement.order_by(BreedingAssessmentModel.date.desc(), BreedingAssessmentModel.created_at.desc(), BreedingAssessmentModel.id).offset(offset).limit(limit))
        return dict(items=[self.response(r) for r in rows], total=total, offset=offset, limit=limit)

    def create(self, data, actor):
        if data.rubric_version != VERSION:
            raise ApplicationError('Breeding assessment criteria changed; reload the form', 409)
        reference = self.db.get(EventModel, str(data.birth_event_id))
        if reference is None:
            raise ApplicationError('Assessment birth not found', 422)
        ids = sorted({reference.animal_id, str(data.offspring_id) if data.offspring_id else reference.animal_id})
        animals = {a.id:a for a in self.db.scalars(select(AnimalModel).where(AnimalModel.id.in_(ids)).order_by(AnimalModel.id).with_for_update())}
        self.db.expire(reference)
        event = self.db.scalar(select(EventModel).join(EventBirthModel, EventBirthModel.event_id == EventModel.id)
                               .where(EventModel.id == str(data.birth_event_id)).with_for_update())
        if event is None:
            raise ApplicationError('Assessment birth not found', 422)
        if self.db.scalar(select(EventModel.id).where(EventModel.replaced_event_id == event.id).limit(1).with_for_update()):
            raise ApplicationError('Assessment birth has been replaced', 409)
        if data.date < event.date.date():
            raise ApplicationError('Assessment date is before birth event', 422)
        subject_id = event.animal_id
        if data.kind == 'offspring':
            subject_id = str(data.offspring_id)
            child = self.db.scalar(select(BirthOffspringModel).where(BirthOffspringModel.event_id == event.id, BirthOffspringModel.animal_id == subject_id).with_for_update())
            if child is None or subject_id not in animals:
                raise ApplicationError('Assessment offspring does not belong to birth', 422)
        subject = animals[subject_id]
        if subject.birth_date and data.date < subject.birth_date:
            raise ApplicationError('Assessment date is before animal birth', 422)
        ensure_in_herd(self.db, subject_id, data.date)
        father_id = subject.father_id if data.kind == 'offspring' else None
        findings = [dict(**c, observation=data.findings.get(c['code'])) for c in CRITERIA[data.kind]]
        row = BreedingAssessmentModel(birth_event_id=event.id, animal_id=subject_id, mother_id=event.animal_id, father_id=father_id,
            kind=data.kind, date=data.date, evaluated_by=data.evaluated_by, rubric_version=VERSION, findings=findings,
            notes=data.notes or None, user_id=actor.id, role_id=actor.role.id)
        self.db.add(row);self.db.flush()
        self.db.add(AuditModel(table='breeding_assessments', record_id=row.id, user_id=actor.id, action='INSERT',
            new_values=dict(birth_event_id=event.id, animal_id=subject_id, mother_id=event.animal_id, father_id=father_id,
                kind=row.kind, date=data.date.isoformat(), evaluated_by=row.evaluated_by, rubric_version=VERSION,
                findings=findings, notes=row.notes, role_id=actor.role.id)))
        self.db.flush()
        return self.response(row)


def repository(db: Session = Depends(get_db, scope='function')):
    return SQLAssessmentRepository(db)


@router.get('/criteria')
def criteria(kind: Kind, actor=Depends(require_permission('breeding:read'))):
    return dict(version=VERSION, scoring='descriptive', criteria=CRITERIA[kind])


@router.get('/birth-options')
def births(q: str = Query('', max_length=100), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
           actor=Depends(require_permission('breeding:read')), repo=Depends(repository)):
    return repo.birth_options(q.strip(), offset, limit)


@router.get('')
def listing(q: str = Query('', max_length=100), kind: Kind | None = None, animal_id: UUID | None = None,
            birth_event_id: UUID | None = None, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
            actor=Depends(require_permission('breeding:read')), repo=Depends(repository)):
    return repo.page(q.strip(), kind, str(animal_id) if animal_id else None, str(birth_event_id) if birth_event_id else None, offset, limit)


@router.post('', status_code=201)
def create(data: AssessmentInput, actor=Depends(require_permission('breeding:write')), repo=Depends(repository)):
    return repo.create(data, actor)
