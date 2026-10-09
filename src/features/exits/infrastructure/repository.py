from datetime import date, datetime, time, timedelta
from sqlalchemy import func, or_, select
from src.core.errors import ApplicationError
from src.core.herd import effective_exit_query, has_exited
from src.core.models import (AnimalModel, AuditModel, BirthOffspringModel,
    EventMatingModel, EventModel, EventTreatmentModel, ExitModel, GroupAnimalModel,
    HealthCaseModel, UserModel)


class SQLExitRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def summary(animal):
        return dict(id=animal.id, name=animal.name, siniiga=animal.siniiga)

    def animal(self, animal_id, lock=False):
        statement = select(AnimalModel).where(AnimalModel.id == animal_id)
        row = self.db.scalar(statement.with_for_update() if lock else statement)
        if row is None:
            raise ApplicationError('Animal not found', 404)
        return row

    def options(self, q):
        statement = select(AnimalModel).where(~has_exited(AnimalModel.id))
        if q:
            statement = statement.where(or_(AnimalModel.name.icontains(q, autoescape=True),
                AnimalModel.siniiga.icontains(q, autoescape=True)))
        return [self.summary(a) for a in self.db.scalars(statement.order_by(AnimalModel.name, AnimalModel.id).limit(100))]

    def query(self):
        return effective_exit_query().add_columns(AnimalModel, UserModel).join(
            AnimalModel, AnimalModel.id == EventModel.animal_id).join(UserModel, UserModel.id == EventModel.user_id)

    def response(self, row):
        event, departure, animal, user = row
        return dict(id=event.id, animal=self.summary(animal), exit_type=departure.exit_type,
            date=event.date.date(), reason=event.reason,
            recorded_by=' '.join(filter(None, [user.name,user.middle_name,user.paternal_lastname,user.maternal_lastname])))

    def page(self, q, exit_type, offset, limit):
        statement = self.query()
        if q:
            statement = statement.where(or_(AnimalModel.name.icontains(q, autoescape=True),
                AnimalModel.siniiga.icontains(q, autoescape=True)))
        if exit_type:
            statement = statement.where(ExitModel.exit_type == exit_type)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.execute(statement.order_by(EventModel.date.desc(),EventModel.created_at.desc(),EventModel.id).offset(offset).limit(limit))
        return dict(items=[self.response(r) for r in rows], total=total, offset=offset, limit=limit)

    def history(self, animal_id):
        animal = self.animal(animal_id)
        rows = self.db.execute(self.query().where(EventModel.animal_id == animal_id).order_by(EventModel.date.desc(),EventModel.id))
        return dict(animal=self.summary(animal), items=[self.response(r) for r in rows])

    def create(self, data, actor):
        animal = self.animal(str(data.animal_id), lock=True)
        if self.db.scalar(effective_exit_query().with_only_columns(EventModel.id).where(EventModel.animal_id == animal.id).limit(1).with_for_update()):
            raise ApplicationError('Animal already has an exit', 409)
        if animal.birth_date and data.date < animal.birth_date:
            raise ApplicationError('Exit date is before birth date', 422)
        end = datetime.combine(data.date, time.max)
        later_event = self.db.scalar(select(EventModel.id).where(EventModel.animal_id == animal.id, EventModel.date > end).limit(1).with_for_update())
        later_mating = self.db.scalar(select(EventModel.id).join(EventMatingModel,EventMatingModel.event_id == EventModel.id).where(EventMatingModel.male_id == animal.id, EventModel.date > end).limit(1).with_for_update())
        later_birth = self.db.scalar(select(BirthOffspringModel.animal_id).join(AnimalModel,AnimalModel.id == BirthOffspringModel.animal_id).join(EventModel,EventModel.id == BirthOffspringModel.event_id).where(AnimalModel.father_id == animal.id, EventModel.date > end).limit(1).with_for_update())
        later_case = self.db.scalar(select(HealthCaseModel.id).where(HealthCaseModel.animal_id == animal.id,HealthCaseModel.start_date > data.date).limit(1).with_for_update())
        later_treatment = self.db.scalar(select(EventTreatmentModel.event_id).join(EventModel,EventModel.id == EventTreatmentModel.event_id).where(EventModel.animal_id == animal.id,EventTreatmentModel.end_date > data.date + timedelta(days=1)).limit(1).with_for_update())
        periods = self.db.scalars(select(GroupAnimalModel).where(GroupAnimalModel.animal_id == animal.id).with_for_update()).all()
        if later_event or later_mating or later_birth or later_case or later_treatment or any(p.start_date > data.date or p.end_date and p.end_date > data.date for p in periods):
            raise ApplicationError('Exit date conflicts with animal history', 422)
        for period in periods:
            if period.end_date is None:
                before = dict(group_id=period.group_id,animal_id=animal.id,start_date=period.start_date.isoformat(),end_date=None)
                period.end_date = data.date
                self.db.add(AuditModel(user_id=actor.id,table='group_animals',record_id=animal.id,action='UPDATE',old_values=before,new_values={**before,'end_date':data.date.isoformat()}))
        event = EventModel(animal_id=animal.id,event_type_id=8,date=datetime.combine(data.date,time.min),user_id=actor.id,role_id=actor.role.id,reason=data.reason)
        self.db.add(event); self.db.flush()
        self.db.add(ExitModel(event_id=event.id,event_type_id=8,exit_type=data.exit_type))
        self.db.add(AuditModel(user_id=actor.id,table='events',record_id=event.id,action='INSERT',new_values=dict(event_type_id=8,role_id=actor.role.id,**data.model_dump(mode='json'))))
        self.db.flush()
        return self.response(self.db.execute(self.query().where(EventModel.id == event.id)).one())
