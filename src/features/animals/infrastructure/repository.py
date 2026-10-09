from src.core.herd import exit_state, has_exited
from datetime import date, datetime
from sqlalchemy import func, or_, select
from src.core.errors import ApplicationError
from src.core.models import AnimalBreedModel, AnimalModel, AuditModel, BreedModel, GroupAnimalModel, EventModel, HealthCaseModel, BirthOffspringModel, EventMatingModel
from src.features.animals.domain.dto import AnimalPage, AnimalResponse, BreedResponse, BreedShareResponse, ParentResponse


class SQLAnimalRepository:
    def __init__(self, session):
        self.session = session

    def _row(self, animal_id):
        row = self.session.get(AnimalModel, animal_id)
        if row is None:
            raise ApplicationError('Animal not found', 404)
        return row

    def _response(self, row):
        def parent(parent_id):
            if not parent_id:
                return None
            item = self._row(parent_id)
            return ParentResponse(id=item.id, name=item.name, siniiga=item.siniiga)
        status, exit_date = exit_state(self.session, row.id)
        shares = sorted(row.breeds, key=lambda share: share.breed.name.casefold())
        return AnimalResponse(
            **{key: getattr(row, key) for key in ('id', 'name', 'siniiga', 'sex', 'birth_date',
               'origin', 'mother_id', 'father_id', 'is_breeder', 'created_at')},
            breeds=[BreedShareResponse(breed_id=s.breed_id, name=s.breed.name, percentage=s.percentage) for s in shares],
            status=status, exit_date=exit_date,
            mother=parent(row.mother_id), father=parent(row.father_id),
            purity=('pure' if len(shares) == 1 and shares[0].percentage == 100 else 'crossbred') if shares else None)

    def get(self, animal_id):
        return self._response(self._row(animal_id))

    def list(self, q, sex, offset, limit, exclude_id=None, active=None):
        query = select(AnimalModel)
        if q:
            query = query.where(or_(AnimalModel.name.icontains(q, autoescape=True),
                                    AnimalModel.siniiga.icontains(q, autoescape=True)))
        if sex:
            query = query.where(AnimalModel.sex == sex)
        if active is not None:
            query = query.where(~has_exited(AnimalModel.id, date.today()) if active else has_exited(AnimalModel.id, date.today()))
        if exclude_id:
            query = query.where(AnimalModel.id != exclude_id)
        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.session.scalars(query.order_by(AnimalModel.created_at.desc(), AnimalModel.id)
                                    .offset(offset).limit(limit)).all()
        return AnimalPage(items=[self._response(row) for row in rows], total=total, offset=offset, limit=limit)

    def breeds(self):
        return [BreedResponse(id=b.id, name=b.name) for b in self.session.scalars(
            select(BreedModel).order_by(BreedModel.name)).all()]

    def create_breed(self, name, actor_id):
        if self.session.scalar(select(BreedModel.id).where(func.lower(BreedModel.name) == name.lower())):
            raise ApplicationError('Breed already exists', 409)
        row = BreedModel(name=name)
        self.session.add(row)
        self.session.flush()
        self.session.add(AuditModel(user_id=actor_id, table='breeds', record_id=str(row.id),
                                   action='INSERT', new_values={'id': row.id, 'name': row.name}))
        return BreedResponse(id=row.id, name=row.name)

    def update_breed(self, breed_id, name, actor_id):
        row = self.session.scalar(select(BreedModel).where(BreedModel.id == breed_id).with_for_update())
        if row is None:
            raise ApplicationError('Breed not found', 404)
        duplicate = self.session.scalar(select(BreedModel.id).where(
            func.lower(BreedModel.name) == name.lower(), BreedModel.id != breed_id))
        if duplicate:
            raise ApplicationError('Breed already exists', 409)
        before = {'id': row.id, 'name': row.name}
        row.name = name
        self.session.flush()
        self.session.add(AuditModel(user_id=actor_id, table='breeds', record_id=str(row.id),
                                   action='UPDATE', old_values=before,
                                   new_values={'id': row.id, 'name': row.name}))
        return BreedResponse(id=row.id, name=row.name)

    def delete_breed(self, breed_id, actor_id):
        row = self.session.scalar(select(BreedModel).where(BreedModel.id == breed_id).with_for_update())
        if row is None:
            raise ApplicationError('Breed not found', 404)
        if self.session.scalar(select(AnimalBreedModel.animal_id).where(AnimalBreedModel.breed_id == breed_id).limit(1)):
            raise ApplicationError('Breed is assigned to animals', 409)
        before = {'id': row.id, 'name': row.name}
        self.session.delete(row)
        self.session.flush()
        self.session.add(AuditModel(user_id=actor_id, table='breeds', record_id=str(breed_id),
                                   action='DELETE', old_values=before))

    def _validate_family(self, data, animal_id):
        # Lock the genealogy rows during writes to prevent concurrent complementary cycles.
        rows = self.session.execute(select(AnimalModel.id, AnimalModel.mother_id, AnimalModel.father_id,
                                           AnimalModel.sex, AnimalModel.birth_date)
                                    .order_by(AnimalModel.id).with_for_update()).all()
        family = {row.id: row for row in rows}
        if animal_id and animal_id not in family:
            raise ApplicationError('Animal not found', 404)
        for parent_id, expected_sex in ((data.mother_id, 'female'), (data.father_id, 'male')):
            if not parent_id:
                continue
            parent_id = str(parent_id)
            parent = family.get(parent_id)
            if parent is None:
                raise ApplicationError('Parent not found', 422)
            if parent.sex != expected_sex:
                raise ApplicationError('Parent sex is incompatible', 422)
            if data.birth_date and parent.birth_date and parent.birth_date >= data.birth_date:
                raise ApplicationError('Parent must be born before offspring', 422)
            pending, visited = [parent_id], set()
            while pending:
                current = pending.pop()
                if current == animal_id:
                    raise ApplicationError('Genealogy cannot contain cycles', 422)
                if current in visited:
                    continue
                visited.add(current)
                ancestor = family.get(current)
                if ancestor:
                    pending.extend(p for p in (ancestor.mother_id, ancestor.father_id) if p)
        if animal_id and data.birth_date and self.session.scalar(select(GroupAnimalModel.animal_id).where(
            GroupAnimalModel.animal_id == animal_id, GroupAnimalModel.start_date < data.birth_date).limit(1).with_for_update()):
            raise ApplicationError('Birth date conflicts with group history', 422)
        if animal_id and data.birth_date and self.session.scalar(select(EventModel.id).where(
            EventModel.animal_id == animal_id, EventModel.event_type_id == 4, EventModel.date < datetime.combine(data.birth_date, datetime.min.time())).limit(1).with_for_update()):
            raise ApplicationError('Birth date conflicts with weight history', 422)
        if animal_id and data.birth_date and self.session.scalar(select(EventModel.id).where(
            EventModel.animal_id == animal_id, EventModel.event_type_id == 8,
            EventModel.date < datetime.combine(data.birth_date, datetime.min.time())).limit(1).with_for_update()):
            raise ApplicationError('Exit date is before birth date', 422)
        if animal_id and data.birth_date and (self.session.scalar(select(HealthCaseModel.id).where(HealthCaseModel.animal_id == animal_id, HealthCaseModel.start_date < data.birth_date).limit(1).with_for_update()) or self.session.scalar(select(EventModel.id).where(EventModel.animal_id == animal_id, EventModel.event_type_id == 1, EventModel.date < datetime.combine(data.birth_date, datetime.min.time())).limit(1).with_for_update())):
            raise ApplicationError('Birth date conflicts with health history', 422)
        if animal_id:
            current=family[animal_id]
            if self.session.get(BirthOffspringModel,animal_id) and (data.birth_date!=current.birth_date or (str(data.mother_id) if data.mother_id else None)!=current.mother_id or (str(data.father_id) if data.father_id else None)!=current.father_id):
                raise ApplicationError('Birth-linked parentage and birth date cannot be changed',422)
            reproductive=self.session.scalars(select(EventModel).where(EventModel.animal_id==animal_id,EventModel.event_type_id.in_([5,6,7]))).all()
            male_events=self.session.scalars(select(EventModel).join(EventMatingModel,EventMatingModel.event_id==EventModel.id).where(EventMatingModel.male_id==animal_id)).all()
            if reproductive and data.sex!='female' or male_events and data.sex!='male':
                raise ApplicationError('Sex conflicts with reproductive history',422)
            if data.birth_date and any(data.birth_date>=e.date.date() for e in reproductive+male_events):
                raise ApplicationError('Birth date conflicts with reproductive history',422)
        if animal_id:
            for child in rows:
                if child.mother_id == animal_id and data.sex != 'female' or child.father_id == animal_id and data.sex != 'male':
                    raise ApplicationError('Sex conflicts with existing offspring', 422)
                if animal_id in (child.mother_id, child.father_id) and data.birth_date and child.birth_date and data.birth_date >= child.birth_date:
                    raise ApplicationError('Parent must be born before offspring', 422)

    def save(self, data, actor_id, animal_id=None):
        self._validate_family(data, animal_id)
        row = self._row(animal_id) if animal_id else AnimalModel()
        before = self._response(row).model_dump(mode='json') if animal_id else None
        if data.siniiga:
            duplicate = self.session.scalar(select(AnimalModel.id).where(
                func.lower(AnimalModel.siniiga) == data.siniiga.lower(), AnimalModel.id != (animal_id or '')))
            if duplicate:
                raise ApplicationError('SINIIGA already exists', 409)
        ids = [share.breed_id for share in data.breeds]
        existing = set(self.session.scalars(select(BreedModel.id).where(BreedModel.id.in_(ids))).all()) if ids else set()
        if existing != set(ids):
            raise ApplicationError('Breed not found', 422)
        values = data.model_dump(exclude={'breeds'})
        for key in ('mother_id', 'father_id'):
            values[key] = str(values[key]) if values[key] else None
        for key, value in values.items():
            setattr(row, key, value)
        self.session.add(row)
        # Reuse existing share objects to avoid delete/insert conflicts on their composite key.
        old = {share.breed_id: share for share in row.breeds}
        shares = []
        for share in data.breeds:
            item = old.get(share.breed_id) or AnimalBreedModel(breed_id=share.breed_id)
            item.percentage = share.percentage
            shares.append(item)
        row.breeds = shares
        self.session.flush()
        self.session.expire(row, ['breeds'])
        response = self._response(row)
        self.session.add(AuditModel(user_id=actor_id, table='animals', record_id=row.id,
                                   action='UPDATE' if animal_id else 'INSERT', old_values=before,
                                   new_values=response.model_dump(mode='json')))
        self.session.flush()
        return response
