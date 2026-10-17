from datetime import date, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import ensure_in_herd, has_exited
from src.core.models import (AnimalModel, AuditModel, CaseFollowupModel, EventModel,
                            EventTreatmentModel, HealthCaseModel, UserModel)
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.health.domain.dto import FollowupInput, FollowupResponse, ReviewPage
from .repository import SQLHealthRepository

router = APIRouter(prefix='/health', tags=['Clinical followup'])


class SQLFollowupRepository(SQLHealthRepository):
    def response(self, followup, case, animal, user):
        return dict(id=followup.id, health_case_id=case.id, animal=self.summary(animal),
            date=followup.date, evolution=followup.evolution, treatment_result=followup.treatment_result,
            notes=followup.notes, next_review_date=followup.next_review_date,
            recorded_by=self.user_name(user), created_at=followup.created_at.replace(tzinfo=timezone.utc).isoformat())

    def query(self):
        return select(CaseFollowupModel, HealthCaseModel, AnimalModel, UserModel).join(
            HealthCaseModel, HealthCaseModel.id == CaseFollowupModel.health_case_id).join(
            AnimalModel, AnimalModel.id == HealthCaseModel.animal_id).join(
            UserModel, UserModel.id == CaseFollowupModel.user_id)

    def followups(self, *, case_id=None, animal_id=None):
        statement = self.query()
        if case_id:
            statement = statement.where(HealthCaseModel.id == case_id)
        if animal_id:
            statement = statement.where(AnimalModel.id == animal_id)
        return [self.response(*row) for row in self.db.execute(statement.order_by(
            CaseFollowupModel.date.desc(), CaseFollowupModel.created_at.desc(), CaseFollowupModel.id.desc()))]

    def create(self, case_id, data, actor):
        case = self.case(case_id)
        animal = self.animal(case.animal_id, True)
        self.db.expire(case)
        case = self.case(case_id, True)
        if case.status == 'closed':
            raise ApplicationError('Health case is closed', 409)
        if data.date < case.start_date:
            raise ApplicationError('Followup date is before case start', 422)
        ensure_in_herd(self.db, animal.id, data.date)
        if data.treatment_result != 'not_assessed':
            replacement = select(EventModel.id).where(EventModel.replaced_event_id == EventTreatmentModel.event_id).correlate(EventTreatmentModel)
            if not self.db.scalar(select(EventTreatmentModel.event_id).where(
                EventTreatmentModel.health_case_id == case.id, EventTreatmentModel.start_date <= data.date,
                ~exists(replacement)).limit(1)):
                raise ApplicationError('Treatment result requires a recorded case treatment', 422)
        row = CaseFollowupModel(health_case_id=case.id, user_id=actor.id, role_id=actor.role.id,
                                **data.model_dump(mode='python'))
        self.db.add(row); self.db.flush()
        self.db.add(AuditModel(table='health_case_followups', record_id=row.id, user_id=actor.id,
            action='INSERT', new_values=dict(health_case_id=case.id, animal_id=animal.id,
                role_id=actor.role.id, **data.model_dump(mode='json'))))
        self.db.flush()
        return self.response(row, case, animal, self.db.get(UserModel, actor.id))

    def reviews(self, q, state, offset, limit):
        latest = select(CaseFollowupModel.id.label('id'), func.row_number().over(
            partition_by=CaseFollowupModel.health_case_id, order_by=(CaseFollowupModel.date.desc(),
            CaseFollowupModel.created_at.desc(), CaseFollowupModel.id.desc())).label('position')).subquery()
        statement = self.search(self.query().join(latest, latest.c.id == CaseFollowupModel.id).where(
            latest.c.position == 1, HealthCaseModel.status != 'closed',
            CaseFollowupModel.next_review_date.is_not(None), ~has_exited(AnimalModel.id, date.today())), q)
        if state == 'attention':
            statement = statement.where(CaseFollowupModel.next_review_date <= date.today())
        elif state == 'upcoming':
            statement = statement.where(CaseFollowupModel.next_review_date > date.today())
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        items = []
        for f, c, a, u in self.db.execute(statement.order_by(CaseFollowupModel.next_review_date,
                HealthCaseModel.id).offset(offset).limit(limit)):
            review_status = 'overdue' if f.next_review_date < date.today() else 'due' if f.next_review_date == date.today() else 'upcoming'
            items.append(dict(case=self.case_response(c,a), followup=self.response(f,c,a,u),
                              next_review_date=f.next_review_date, status=review_status))
        return dict(items=items, total=total, offset=offset, limit=limit, as_of=date.today())


def repository(db: Session = Depends(get_db, scope='function')):
    return SQLFollowupRepository(db)


@router.post('/cases/{case_id}/followups', response_model=FollowupResponse, status_code=201)
def create(case_id: UUID, data: FollowupInput, actor=Depends(require_permission('health:followups:create')),
           repo=Depends(repository)):
    return repo.create(str(case_id),data,actor)


@router.get('/reviews', response_model=ReviewPage)
def reviews(q: str = Query('', max_length=100), state: Literal['all','attention','upcoming'] = 'attention',
            offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
            actor=Depends(require_permission('health:read')), repo=Depends(repository)):
    return repo.reviews(q.strip(), state, offset, limit)
