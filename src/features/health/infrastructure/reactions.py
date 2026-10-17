"""Observed adverse reactions and suspected allergies; recording does not establish causality."""
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import ensure_in_herd
from src.core.models import AnimalReactionModel, AnimalModel, ProductModel, TreatmentDoseModel, EventModel, UserModel, AuditModel
from src.features.auth.infrastructure.dependencies import require_permission
from .repository import SQLHealthRepository
from .doses import SQLDoseRepository

router = APIRouter(prefix='/health/reactions', tags=['Allergies and adverse reactions'])


class DatedInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    date: date

    @field_validator('date')
    @classmethod
    def not_future(cls, value):
        if value > date.today():
            raise ValueError('Reaction date cannot be in the future')
        return value


class ReactionInput(DatedInput):
    animal_id: UUID
    kind: Literal['suspected_allergy', 'adverse_reaction']
    description: str = Field(min_length=1, max_length=5000)
    suspected_agent: str | None = Field(default=None, max_length=190)
    product_id: UUID | None = None
    dose_id: UUID | None = None


class ClosureInput(DatedInput):
    notes: str = Field(min_length=1, max_length=5000)


class SQLReactionRepository(SQLHealthRepository):
    def response(self, row):
        product = self.db.get(ProductModel, row.product_id) if row.product_id else None
        dose = self.db.get(TreatmentDoseModel, row.dose_id) if row.dose_id else None
        return dict(id=row.id, animal=self.summary(self.animal(row.animal_id)), date=row.date,
            kind=row.kind, description=row.description, suspected_agent=row.suspected_agent,
            product_id=row.product_id, product_name=product.name if product else None,
            dose=SQLDoseRepository(self.db).response(dose) if dose else None,
            recorded_by=self.user_name(self.db.get(UserModel,row.user_id)),
            status='closed' if row.closed_date else 'open', closed_date=row.closed_date,
            closure_notes=row.closure_notes,
            closed_by=self.user_name(self.db.get(UserModel,row.closed_by)) if row.closed_by else None)

    def page(self, q, animal_id, status, offset, limit):
        statement=self.search(select(AnimalReactionModel).join(AnimalModel,AnimalModel.id==AnimalReactionModel.animal_id),q)
        if animal_id:
            self.animal(animal_id)
            statement=statement.where(AnimalReactionModel.animal_id==animal_id)
        if status:
            statement=statement.where(AnimalReactionModel.closed_date.is_(None) if status=='open' else AnimalReactionModel.closed_date.is_not(None))
        total=self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows=self.db.scalars(statement.order_by(AnimalReactionModel.date.desc(),AnimalReactionModel.created_at.desc(),AnimalReactionModel.id).offset(offset).limit(limit))
        return dict(items=[self.response(r) for r in rows],total=total,offset=offset,limit=limit)

    def create(self,data,actor):
        animal=self.animal(str(data.animal_id),True)
        if animal.birth_date and data.date<animal.birth_date:
            raise ApplicationError('Reaction date is before birth date',422)
        ensure_in_herd(self.db,animal.id,data.date)
        product_id=str(data.product_id) if data.product_id else None
        dose_id=str(data.dose_id) if data.dose_id else None
        if dose_id:
            dose=self.db.scalar(select(TreatmentDoseModel).where(TreatmentDoseModel.id==dose_id).with_for_update())
            if dose is None:
                raise ApplicationError('Applied dose not found',422)
            event=self.db.get(EventModel,dose.treatment_event_id)
            if event.animal_id!=animal.id:
                raise ApplicationError('Applied dose belongs to another animal',422)
            if data.date<dose.clinical_date:
                raise ApplicationError('Reaction date is before applied dose',422)
            if product_id and product_id!=dose.product_id:
                raise ApplicationError('Product differs from applied dose',422)
            product_id=dose.product_id
        if product_id and not self.db.get(ProductModel,product_id):
            raise ApplicationError('Product not found',422)
        # Historical reports may reference inactive products and replaced treatment instructions.
        row=AnimalReactionModel(animal_id=animal.id,date=data.date,kind=data.kind,description=data.description,
            suspected_agent=data.suspected_agent or None,product_id=product_id,dose_id=dose_id,user_id=actor.id,role_id=actor.role.id)
        self.db.add(row);self.db.flush()
        self.db.add(AuditModel(table='animal_reactions',record_id=row.id,user_id=actor.id,action='INSERT',
            new_values={**data.model_dump(mode='json'),'product_id':product_id,'role_id':actor.role.id}))
        self.db.flush()
        return self.response(row)

    def close(self,reaction_id,data,actor):
        reference=self.db.get(AnimalReactionModel,reaction_id)
        if reference is None:
            raise ApplicationError('Reaction not found',404)
        self.animal(reference.animal_id,True)
        self.db.expire(reference)
        row=self.db.scalar(select(AnimalReactionModel).where(AnimalReactionModel.id==reaction_id).with_for_update())
        if row.closed_date:
            raise ApplicationError('Reaction follow-up is already closed',409)
        if data.date<row.date:
            raise ApplicationError('Closure date is before reaction date',422)
        # Administrative follow-up may close after exit; it is not a new clinical administration.
        row.closed_date=data.date;row.closure_notes=data.notes;row.closed_by=actor.id
        row.closure_role_id=actor.role.id;row.closed_at=datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.add(AuditModel(table='animal_reactions',record_id=row.id,user_id=actor.id,action='UPDATE',
            old_values={'status':'open'},new_values={'status':'closed','closed_date':data.date.isoformat(),
            'closure_notes':data.notes,'role_id':actor.role.id}))
        self.db.flush()
        return self.response(row)

    def doses(self,animal_id,product_id,offset,limit):
        self.animal(animal_id)
        statement=select(TreatmentDoseModel).join(EventModel,EventModel.id==TreatmentDoseModel.treatment_event_id).where(EventModel.animal_id==animal_id)
        if product_id:
            statement=statement.where(TreatmentDoseModel.product_id==product_id)
        total=self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows=self.db.scalars(statement.order_by(TreatmentDoseModel.applied_at_utc.desc(),TreatmentDoseModel.id).offset(offset).limit(limit))
        repo=SQLDoseRepository(self.db)
        return dict(items=[{**repo.response(r),'product_name':self.db.get(ProductModel,r.product_id).name} for r in rows],total=total,offset=offset,limit=limit)


def repository(db:Session=Depends(get_db,scope='function')):
    return SQLReactionRepository(db)


@router.get('')
def listing(q:str=Query('',max_length=100),animal_id:UUID|None=None,status:Literal['open','closed']|None=None,
            offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),
            actor=Depends(require_permission('health:read')),repo=Depends(repository)):
    return repo.page(q.strip(),str(animal_id) if animal_id else None,status,offset,limit)


@router.get('/dose-options')
def doses(animal_id:UUID,product_id:UUID|None=None,offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),
          actor=Depends(require_permission('health:read')),repo=Depends(repository)):
    return repo.doses(str(animal_id),str(product_id) if product_id else None,offset,limit)


@router.post('',status_code=201)
def create(data:ReactionInput,actor=Depends(require_permission('health:reactions:write')),repo=Depends(repository)):
    return repo.create(data,actor)


@router.post('/{reaction_id}/closure')
def close(reaction_id:UUID,data:ClosureInput,actor=Depends(require_permission('health:reactions:write')),repo=Depends(repository)):
    return repo.close(str(reaction_id),data,actor)
