from datetime import date, datetime, time, timedelta
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import aliased
from src.core.errors import ApplicationError
from src.core.herd import ensure_in_herd, has_exited
from src.core.models import AnimalModel, AuditModel, EventModel, EventWeightModel, EventWeaningModel, UserModel
from src.features.weights.domain.dto import WeightInput
from src.features.weights.infrastructure.repository import SQLWeightRepository


class SQLWeaningRepository(SQLWeightRepository):
    def options(self, q, limit):
        query = select(AnimalModel).where(~has_exited(AnimalModel.id,date.today()),
            ~exists(select(EventWeaningModel.event_id).where(EventWeaningModel.animal_id == AnimalModel.id)))
        if q:
            query = query.where(or_(AnimalModel.name.icontains(q,autoescape=True),
                                   AnimalModel.siniiga.icontains(q,autoescape=True)))
        return [dict(**self.summary(a),birth_date=a.birth_date,
            mother=self.summary(self.db.get(AnimalModel,a.mother_id)) if a.mother_id else None)
            for a in self.db.scalars(query.order_by(AnimalModel.name,AnimalModel.id).limit(limit))]

    def query(self):
        mother = aliased(AnimalModel)
        return select(EventWeaningModel, EventModel, EventWeightModel, AnimalModel, mother, UserModel).join(
            EventModel, EventModel.id == EventWeaningModel.event_id).join(
            EventWeightModel, EventWeightModel.event_id == EventWeaningModel.event_id).join(
            AnimalModel, AnimalModel.id == EventWeaningModel.animal_id).outerjoin(
            mother,mother.id == EventWeaningModel.mother_id).join(UserModel,UserModel.id == EventWeaningModel.user_id)

    def response(self, row):
        weaning,event,weight,animal,mother,user = row
        return dict(id=event.id, animal=self.summary(animal),mother=self.summary(mother) if mother else None,
            date=event.date.date(),weight_kg=weight.weight_kg,birth_date_snapshot=weaning.birth_date_snapshot,
            age_days=(event.date.date()-weaning.birth_date_snapshot).days if weaning.birth_date_snapshot else None,
            notes=weaning.notes,recorded_by=' '.join(filter(None,[user.name,user.middle_name,user.paternal_lastname,user.maternal_lastname])))

    def page(self, q, offset, limit):
        statement = self.query()
        if q:
            statement = statement.where(or_(AnimalModel.name.icontains(q,autoescape=True),
                                           AnimalModel.siniiga.icontains(q,autoescape=True)))
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.execute(statement.order_by(EventModel.date.desc(),EventModel.created_at.desc(),EventModel.id).offset(offset).limit(limit))
        return dict(items=[self.response(row) for row in rows],total=total,offset=offset,limit=limit)

    def create(self, data, actor):
        animal = self.animal(str(data.animal_id),lock=True)
        if animal.birth_date and data.date <= animal.birth_date:
            raise ApplicationError('Weaning date must be after birth date',422)
        ensure_in_herd(self.db,animal.id,data.date)
        if self.db.scalar(select(EventWeaningModel.event_id).where(EventWeaningModel.animal_id == animal.id).limit(1)):
            raise ApplicationError('Animal already has a weaning record',409)
        # Reuse an effective daily measurement only when the observed value agrees.
        replacement = aliased(EventModel)
        rows = self.db.execute(select(EventModel,EventWeightModel).join(
            EventWeightModel,EventWeightModel.event_id == EventModel.id).where(
            EventModel.animal_id == animal.id,EventModel.date >= datetime.combine(data.date,time.min),
            EventModel.date < datetime.combine(data.date+timedelta(days=1),time.min),
            ~exists(select(replacement.id).where(replacement.replaced_event_id == EventModel.id))).limit(2).with_for_update()).all()
        if len(rows) > 1:
            raise ApplicationError('Multiple weights exist on weaning date',409)
        reused = bool(rows)
        if rows:
            event,weight = rows[0]
            if weight.weight_kg != data.weight_kg:
                raise ApplicationError('Weaning weight differs from existing daily weight',409)
        else:
            saved = SQLWeightRepository(self.db).create(WeightInput(**data.model_dump()),actor)
            event = self.db.get(EventModel,saved['id'])
        weaning = EventWeaningModel(event_id=event.id,animal_id=animal.id,mother_id=animal.mother_id,
            birth_date_snapshot=animal.birth_date,notes=data.notes,user_id=actor.id,role_id=actor.role.id)
        self.db.add(weaning)
        self.db.add(AuditModel(table='event_weanings',record_id=event.id,user_id=actor.id,action='INSERT',
            new_values=dict(mother_id=animal.mother_id,birth_date_snapshot=animal.birth_date.isoformat() if animal.birth_date else None,
                            role_id=actor.role.id,weight_reused=reused,**data.model_dump(mode='json'))))
        self.db.flush()
        return self.response(self.db.execute(self.query().where(EventWeaningModel.event_id == event.id)).one())
