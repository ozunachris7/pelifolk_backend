from src.core.herd import has_exited, effective_exit_query
from src.core.models import EventModel
from src.core.locations import latest_location_event_id
from datetime import date
from sqlalchemy import func, or_, select
from src.core.errors import ApplicationError
from src.core.models import AnimalGroupModel, AnimalModel, AuditModel, GroupAnimalModel, LocationModel, LocationTypeModel
from src.features.organization.domain.dto import AnimalOption, AnimalOptionPage, GroupResponse, LocationResponse, MembershipPage, MembershipResponse, TypeResponse
from src.features.organization.domain.periods import close_period


def current_period():
    today = date.today()
    return (GroupAnimalModel.start_date <= today, or_(GroupAnimalModel.end_date.is_(None), GroupAnimalModel.end_date >= today))


class SQLOrganizationRepository:
    def __init__(self, session):
        self.session = session

    def audit(self, table, record_id, actor_id, before, after):
        self.session.add(AuditModel(user_id=actor_id, table=table, record_id=record_id,
                                   action='UPDATE' if before else 'INSERT', old_values=before, new_values=after))

    def types(self):
        return [TypeResponse(id=row.id, name=row.name) for row in self.session.scalars(
            select(LocationTypeModel).order_by(LocationTypeModel.name))]

    def create_type(self, name, actor_id):
        if self.session.scalar(select(LocationTypeModel.id).where(func.lower(LocationTypeModel.name) == name.lower())):
            raise ApplicationError('Location type already exists', 409)
        row = LocationTypeModel(name=name)
        self.session.add(row)
        self.session.flush()
        response = TypeResponse(id=row.id, name=row.name)
        self.audit('location_types', str(row.id), actor_id, None, response.model_dump())
        return response

    def location_response(self, row):
        return LocationResponse(id=row.id, name=row.name, description=row.description, active=row.active,
                                location_type_id=row.location_type_id, location_type_name=row.location_type.name)

    def locations(self, q, active):
        query = select(LocationModel).order_by(LocationModel.name)
        if q:
            query = query.where(LocationModel.name.icontains(q, autoescape=True))
        if active is not None:
            query = query.where(LocationModel.active == active)
        return [self.location_response(row) for row in self.session.scalars(query)]

    def save_location(self, data, actor_id, location_id=None):
        row = self.session.get(LocationModel, location_id, with_for_update=True) if location_id else LocationModel()
        if row is None:
            raise ApplicationError('Location not found', 404)
        before = self.location_response(row).model_dump() if location_id else None
        if location_id and not data.active and self.session.scalar(select(AnimalModel.id).join(EventModel, EventModel.id == latest_location_event_id()).where(
            EventModel.location_id == location_id, ~has_exited(AnimalModel.id, date.today())).limit(1)):
            raise ApplicationError('Location has assigned animals', 409)
        kind = self.session.get(LocationTypeModel, data.location_type_id)
        if kind is None:
            raise ApplicationError('Location type not found', 422)
        if self.session.scalar(select(LocationModel.id).where(func.lower(LocationModel.name) == data.name.lower(),
                                                             LocationModel.id != (location_id or ''))):
            raise ApplicationError('Location name already exists', 409)
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        row.location_type = kind
        self.session.add(row)
        self.session.flush()
        response = self.location_response(row)
        self.audit('locations', row.id, actor_id, before, response.model_dump())
        return response

    def group(self, group_id, lock=False):
        row = self.session.get(AnimalGroupModel, group_id, with_for_update=lock)
        if row is None:
            raise ApplicationError('Group not found', 404)
        return row

    def group_response(self, row, count=None):
        if count is None:
            count = self.session.scalar(select(func.count()).select_from(GroupAnimalModel).where(
                GroupAnimalModel.group_id == row.id, *current_period(), ~has_exited(GroupAnimalModel.animal_id, date.today())))
        return GroupResponse(id=row.id, name=row.name, description=row.description, active=row.active, member_count=count)

    def groups(self, q, active):
        counts = select(GroupAnimalModel.group_id, func.count().label('count')).where(*current_period(), ~has_exited(GroupAnimalModel.animal_id, date.today())).group_by(GroupAnimalModel.group_id).subquery()
        query = select(AnimalGroupModel, func.coalesce(counts.c.count, 0)).outerjoin(counts, counts.c.group_id == AnimalGroupModel.id).order_by(AnimalGroupModel.name)
        if q:
            query = query.where(AnimalGroupModel.name.icontains(q, autoescape=True))
        if active is not None:
            query = query.where(AnimalGroupModel.active == active)
        return [self.group_response(row, count) for row, count in self.session.execute(query)]

    def save_group(self, data, actor_id, group_id=None):
        row = self.group(group_id, lock=True) if group_id else AnimalGroupModel()
        before = self.group_response(row).model_dump() if group_id else None
        if group_id and not data.active and self.session.scalar(select(GroupAnimalModel.animal_id).where(
            GroupAnimalModel.group_id == group_id, or_(GroupAnimalModel.end_date.is_(None), GroupAnimalModel.end_date >= date.today())).limit(1)):
            raise ApplicationError('Group has assigned animals', 409)
        if self.session.scalar(select(AnimalGroupModel.id).where(func.lower(AnimalGroupModel.name) == data.name.lower(),
                                                                AnimalGroupModel.id != (group_id or ''))):
            raise ApplicationError('Group name already exists', 409)
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        self.session.add(row)
        self.session.flush()
        response = self.group_response(row)
        self.audit('animal_groups', row.id, actor_id, before, response.model_dump())
        return response

    def membership_response(self, row, animal=None, group=None):
        animal = animal or self.session.get(AnimalModel, row.animal_id)
        group = group or self.group(row.group_id)
        return MembershipResponse(group_id=row.group_id, group_name=group.name, animal_id=row.animal_id,
                                  animal_name=animal.name, siniiga=animal.siniiga, start_date=row.start_date, end_date=row.end_date)

    def memberships(self, group_id, current, offset, limit):
        group = self.group(group_id)
        query = select(GroupAnimalModel, AnimalModel).join(AnimalModel, AnimalModel.id == GroupAnimalModel.animal_id).where(GroupAnimalModel.group_id == group_id)
        if current:
            query = query.where(*current_period(), ~has_exited(GroupAnimalModel.animal_id, date.today()))
        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.session.execute(query.order_by(GroupAnimalModel.start_date.desc(), GroupAnimalModel.animal_id).offset(offset).limit(limit))
        return MembershipPage(items=[self.membership_response(row, animal, group) for row, animal in rows], total=total, offset=offset, limit=limit)

    def animal_options(self, q, limit):
        period_start, period_end = current_period()
        query = select(AnimalModel.id, AnimalModel.name, AnimalModel.siniiga,
                       AnimalGroupModel.id.label('group_id'), AnimalGroupModel.name.label('group_name')).outerjoin(
            GroupAnimalModel, (GroupAnimalModel.animal_id == AnimalModel.id) & period_start & period_end).outerjoin(
            AnimalGroupModel, AnimalGroupModel.id == GroupAnimalModel.group_id)
        query = query.where(~has_exited(AnimalModel.id))
        if q:
            query = query.where(or_(AnimalModel.name.icontains(q, autoescape=True), AnimalModel.siniiga.icontains(q, autoescape=True)))
        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        return AnimalOptionPage(items=[AnimalOption(**row._mapping) for row in self.session.execute(query.order_by(AnimalModel.name, AnimalModel.id).limit(limit))], total=total)

    def assign(self, group_id, data, actor_id):
        target = self.group(group_id, lock=True)
        if not target.active:
            raise ApplicationError('Group is inactive', 409)
        ids = sorted(str(animal_id) for animal_id in data.animal_ids)
        animals = self.session.execute(select(AnimalModel.id, AnimalModel.birth_date).where(AnimalModel.id.in_(ids)).order_by(AnimalModel.id).with_for_update()).all()
        if len(animals) != len(ids):
            raise ApplicationError('Animal not found', 404)
        histories = self.session.scalars(select(GroupAnimalModel).where(GroupAnimalModel.animal_id.in_(ids)).order_by(
            GroupAnimalModel.animal_id, GroupAnimalModel.start_date.desc()).with_for_update()).all()
        plans = []
        for animal in animals:
            if self.session.scalar(effective_exit_query().with_only_columns(EventModel.id).where(EventModel.animal_id == animal.id).limit(1).with_for_update()):
                raise ApplicationError('Animal already has an exit', 409)
            if animal.birth_date and data.effective_date < animal.birth_date:
                raise ApplicationError('Movement date cannot precede birth', 422)
            periods = [period for period in histories if period.animal_id == animal.id]
            open_periods = [period for period in periods if period.end_date is None]
            if len(open_periods) > 1:
                raise ApplicationError('Movement overlaps existing history', 409)
            current = next(iter(open_periods), None)
            if current:
                if current.group_id == group_id:
                    raise ApplicationError('Animal already belongs to this group', 409)
                if not data.move_existing:
                    raise ApplicationError('Animal already belongs to another group', 409)
                end = close_period(current.start_date, data.effective_date)
                # Closed periods after the open record also forbid backdated changes.
                if any(p is not current and p.end_date >= data.effective_date for p in periods):
                    raise ApplicationError('Movement overlaps existing history', 409)
            else:
                end = None
                if any(period.end_date >= data.effective_date for period in periods):
                    raise ApplicationError('Movement overlaps existing history', 409)
            plans.append((animal.id, current, end))
        # Validate the whole batch before writing. Flush closures before inserts for MySQL overlap triggers.
        for animal_id, current, end in plans:
            if current:
                before = self.membership_response(current).model_dump(mode='json')
                current.end_date = end
                self.audit('group_animals', animal_id, actor_id, before, self.membership_response(current).model_dump(mode='json'))
        self.session.flush()
        result = []
        for animal_id, current, end in plans:
            row = GroupAnimalModel(group_id=group_id, animal_id=animal_id, start_date=data.effective_date)
            self.session.add(row)
            response = self.membership_response(row, group=target)
            result.append(response)
            self.audit('group_animals', animal_id, actor_id, None, response.model_dump(mode='json'))
        self.session.flush()
        return result

    def remove(self, group_id, animal_id, effective_date, actor_id):
        self.group(group_id, lock=True)
        animal = self.session.scalar(select(AnimalModel.id).where(AnimalModel.id == animal_id).with_for_update())
        if animal is None:
            raise ApplicationError('Animal not found', 404)
        row = self.session.scalar(select(GroupAnimalModel).where(GroupAnimalModel.group_id == group_id,
            GroupAnimalModel.animal_id == animal_id, GroupAnimalModel.end_date.is_(None)).with_for_update())
        if row is None:
            raise ApplicationError('Animal is no longer assigned to this group', 409)
        before = self.membership_response(row).model_dump(mode='json')
        row.end_date = close_period(row.start_date, effective_date)
        self.session.flush()
        response = self.membership_response(row)
        self.audit('group_animals', animal_id, actor_id, before, response.model_dump(mode='json'))
        return response
