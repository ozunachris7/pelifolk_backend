from datetime import date
from src.core.herd import has_exited, ensure_in_herd
from datetime import datetime, time
from sqlalchemy import select, func, or_, exists
from src.core.models import AnimalModel, EventModel, EventWeightModel, UserModel, AuditModel
from src.core.errors import ApplicationError


class SQLWeightRepository:
    def __init__(self, db):
        self.db = db

    def animal(self, animal_id, lock=False):
        statement = select(AnimalModel).where(AnimalModel.id == animal_id)
        if lock:
            statement = statement.with_for_update()
        animal = self.db.scalar(statement)
        if not animal:
            raise ApplicationError('Animal not found', 404)
        return animal

    @staticmethod
    def summary(animal):
        return dict(id=animal.id, name=animal.name, siniiga=animal.siniiga)

    def options(self, q, limit):
        statement = select(AnimalModel).where(~has_exited(AnimalModel.id, date.today()))
        if q:
            statement = statement.where(or_(AnimalModel.name.icontains(q, autoescape=True), AnimalModel.siniiga.icontains(q, autoescape=True)))
        return [self.summary(a) for a in self.db.scalars(statement.order_by(AnimalModel.name, AnimalModel.id).limit(limit))]

    def query(self):
        replacement = select(EventModel.id).where(EventModel.replaced_event_id == EventWeightModel.event_id).correlate(EventWeightModel)
        return select(EventModel, EventWeightModel, AnimalModel, UserModel).join(EventWeightModel, EventWeightModel.event_id == EventModel.id).join(AnimalModel, AnimalModel.id == EventModel.animal_id).join(UserModel, UserModel.id == EventModel.user_id).where(EventModel.event_type_id == 4, ~exists(replacement))

    def response(self, row):
        event, weight, animal, user = row
        return dict(id=event.id, animal=self.summary(animal), date=event.date.date(), weight_kg=weight.weight_kg, notes=event.reason,
                    recorded_by=' '.join(filter(None, [user.name, user.middle_name, user.paternal_lastname, user.maternal_lastname])))

    def page(self, q, offset, limit):
        statement = self.query()
        if q:
            statement = statement.where(or_(AnimalModel.name.icontains(q, autoescape=True), AnimalModel.siniiga.icontains(q, autoescape=True)))
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.execute(statement.order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id).offset(offset).limit(limit))
        return dict(items=[self.response(row) for row in rows], total=total, offset=offset, limit=limit)

    def history(self, animal_id):
        animal = self.animal(animal_id)
        rows = self.db.execute(self.query().where(EventModel.animal_id == animal_id).order_by(EventModel.date, EventModel.created_at, EventModel.id))
        return dict(animal=self.summary(animal), items=[self.response(row) for row in rows])

    def create(self, data, actor):
        animal = self.animal(str(data.animal_id), lock=True)
        if animal.birth_date and data.date < animal.birth_date:
            raise ApplicationError('Weight date is before birth date', 422)
        ensure_in_herd(self.db, animal.id, data.date)
        # One measurement per calendar day makes daily gain unambiguous.
        day = datetime.combine(data.date, time.min)
        if self.db.scalar(select(EventModel.id).join(EventWeightModel, EventWeightModel.event_id == EventModel.id).where(EventModel.animal_id == animal.id, EventModel.date >= day, EventModel.date < datetime.combine(data.date, time.max))):
            raise ApplicationError('Animal already has a weight on this date', 409)
        event = EventModel(animal_id=animal.id, event_type_id=4, date=day, user_id=actor.id, role_id=actor.role.id, reason=data.notes)
        self.db.add(event)
        self.db.flush()
        self.db.add(EventWeightModel(event_id=event.id, event_type_id=4, weight_kg=data.weight_kg))
        self.db.add(AuditModel(user_id=actor.id, table='events', record_id=event.id, action='INSERT', new_values=dict(animal_id=animal.id, event_type_id=4, date=data.date.isoformat(), weight_kg=str(data.weight_kg), reason=data.notes, role_id=actor.role.id)))
        self.db.flush()
        return self.response((event, self.db.get(EventWeightModel, event.id), animal, self.db.get(UserModel, actor.id)))
