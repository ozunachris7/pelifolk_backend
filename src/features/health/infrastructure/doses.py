"""Actual administrations, separate from the recorded treatment instructions."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import ensure_in_herd
from src.core.models import (AdministrationRouteModel, AuditModel, EventModel, EventTreatmentModel,
                             TreatmentDoseModel, UnitModel, UserModel)
from src.features.auth.infrastructure.dependencies import require_permission
from .repository import SQLHealthRepository

router = APIRouter(prefix='/health/treatments', tags=['Actual treatment doses'])


class DoseInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    applied_at: AwareDatetime
    administered_by: str = Field(min_length=1, max_length=190)
    dose_value: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    dose_unit_id: int = Field(gt=0)
    route_id: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator('applied_at')
    @classmethod
    def actual_time(cls, value):
        try:
            instant = value.astimezone(timezone.utc)
        except (OverflowError, ValueError):
            raise ValueError('Invalid application datetime')
        if instant > datetime.now(timezone.utc):
            raise ValueError('Dose application cannot be in the future')
        offset = value.utcoffset().total_seconds()
        if offset % 60 or abs(offset) > 14 * 3600:
            raise ValueError('Invalid application timezone offset')
        return value.replace(microsecond=0)

    @field_validator('notes')
    @classmethod
    def empty_notes(cls, value):
        return value or None


class SQLDoseRepository(SQLHealthRepository):
    def treatment(self, event_id, product_id, lock=False):
        statement = select(EventTreatmentModel).where(EventTreatmentModel.event_id == event_id,
                                                      EventTreatmentModel.product_id == product_id)
        treatment = self.db.scalar(statement.with_for_update() if lock else statement)
        if treatment is None:
            raise ApplicationError('Treatment not found', 404)
        return treatment

    def response(self, row):
        applied_at = row.applied_at_utc.replace(tzinfo=timezone.utc).astimezone(
            timezone(timedelta(minutes=row.utc_offset_minutes)))
        return dict(id=row.id, treatment_event_id=row.treatment_event_id, product_id=row.product_id,
            applied_at=applied_at.isoformat(), administered_by=row.administered_by,
            dose_value=str(row.dose_value), dose_unit_id=row.dose_unit_id,
            dose_unit_code=self.db.get(UnitModel,row.dose_unit_id).code,
            route_id=row.route_id, route_name=self.db.get(AdministrationRouteModel,row.route_id).name,
            notes=row.notes, is_deviation=row.is_deviation,
            recorded_by=self.user_name(self.db.get(UserModel,row.user_id)),
            created_at=row.created_at.replace(tzinfo=timezone.utc).isoformat())

    def page(self, event_id, product_id, offset, limit):
        self.treatment(event_id, product_id)
        statement = select(TreatmentDoseModel).where(TreatmentDoseModel.treatment_event_id == event_id,
                                                     TreatmentDoseModel.product_id == product_id)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.scalars(statement.order_by(TreatmentDoseModel.applied_at_utc.desc(),
            TreatmentDoseModel.created_at.desc(), TreatmentDoseModel.id).offset(offset).limit(limit))
        return dict(items=[self.response(r) for r in rows], total=total, offset=offset, limit=limit)

    def create(self, event_id, product_id, data, actor):
        reference = self.db.get(EventModel, event_id)
        if reference is None:
            raise ApplicationError('Treatment not found', 404)
        animal = self.animal(reference.animal_id, True)
        # Current locking reads avoid stale pre-lock snapshots under MySQL REPEATABLE READ.
        self.db.expire(reference)
        event = self.db.scalar(select(EventModel).where(EventModel.id == event_id).with_for_update())
        treatment = self.treatment(event_id, product_id, True)
        if self.db.scalar(select(EventModel.id).where(EventModel.replaced_event_id == event_id).limit(1).with_for_update()):
            raise ApplicationError('Treatment has been replaced', 409)
        day = data.applied_at.date()
        if animal.birth_date and day < animal.birth_date:
            raise ApplicationError('Health date is before birth date', 422)
        ensure_in_herd(self.db, animal.id, day)
        if treatment.health_case_id:
            case = self.case(treatment.health_case_id, True)
            if case.status == 'closed':
                raise ApplicationError('Reopen case before recording a dose', 409)
            if day < case.start_date:
                raise ApplicationError('Dose date is before case start', 422)
        if not self.db.get(UnitModel,data.dose_unit_id) or not self.db.get(AdministrationRouteModel,data.route_id):
            raise ApplicationError('Treatment catalog entry not found', 422)
        instant = data.applied_at.astimezone(timezone.utc).replace(tzinfo=None)
        if self.db.scalar(select(TreatmentDoseModel.id).where(TreatmentDoseModel.treatment_event_id == event_id,
                TreatmentDoseModel.product_id == product_id, TreatmentDoseModel.applied_at_utc == instant).limit(1).with_for_update()):
            raise ApplicationError('Dose already recorded at this time', 409)
        deviation = (day < treatment.start_date or day >= treatment.end_date or
                     data.dose_value != treatment.dose_value or data.dose_unit_id != treatment.dose_unit_id or
                     data.route_id != treatment.route_id)
        if deviation and not data.notes:
            raise ApplicationError('Dose variation requires explanation', 422)
        row = TreatmentDoseModel(treatment_event_id=event_id, product_id=product_id,
            applied_at_utc=instant, clinical_date=day, utc_offset_minutes=int(data.applied_at.utcoffset().total_seconds()/60),
            administered_by=data.administered_by, dose_value=data.dose_value, dose_unit_id=data.dose_unit_id,
            route_id=data.route_id, notes=data.notes, is_deviation=deviation, user_id=actor.id, role_id=actor.role.id)
        self.db.add(row); self.db.flush()
        self.db.add(AuditModel(table='treatment_doses',record_id=row.id,user_id=actor.id,action='INSERT',
            new_values=dict(treatment_event_id=event_id, product_id=product_id, animal_id=animal.id,
                            role_id=actor.role.id, is_deviation=deviation, **data.model_dump(mode='json'))))
        self.db.flush()
        self.db.refresh(row)
        return self.response(row)


def repository(db: Session = Depends(get_db,scope='function')):
    return SQLDoseRepository(db)


@router.get('/{event_id}/products/{product_id}/doses')
def listing(event_id: UUID, product_id: UUID, offset: int = Query(0,ge=0), limit: int = Query(25,ge=1,le=100),
            actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.page(str(event_id),str(product_id),offset,limit)


@router.post('/{event_id}/products/{product_id}/doses',status_code=201)
def create(event_id: UUID, product_id: UUID, data: DoseInput,
           actor=Depends(require_permission('health:doses:create')), repo=Depends(repository)):
    return repo.create(str(event_id),str(product_id),data,actor)
