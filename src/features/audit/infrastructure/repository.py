from datetime import timezone
from sqlalchemy import case, exists, func, or_, select
from src.core.errors import ApplicationError
from src.core.models import (AnimalModel, AuditModel, EventModel, UserModel, RoleModel,
    AnimalGroupModel, LocationModel, ProductModel, FeedModel, BreedModel, HealthProgramModel,
    UnitModel, AdministrationRouteModel, ExpenseCategoryModel, IncomeCategoryModel, SupplierModel)
from src.features.audit.domain.changes import changed_fields, redact

TABLE_MODULES = {
    'history_rectifications':'animals',
    'animal_incidents':'health', 'incident_followups':'health', 'animal_reactions':'health', 'treatment_doses':'health', 'health_case_observations':'health', 'event_weanings':'weights', 'breeding_assessments':'breeding', 'physical_evaluations':'animals', 'animal_decisions':'animals', 'animals':'animals', 'breeds':'animals', 'animal_breeds':'animals',
    'health_case_followups':'health', 'health_cases':'health', 'products':'health', 'health_programs':'health',
    'product_prices':'health', 'product_ingredients':'health',
    'locations':'locations', 'location_types':'locations',
    'groups':'groups', 'animal_groups':'groups', 'group_animals':'groups',
    'expenses':'finance', 'incomes':'finance', 'suppliers':'finance',
    'expense_categories':'finance', 'income_categories':'finance', 'expense_allocations':'finance',
    'feeds':'feeding', 'feed_prices':'feeding', 'feedings':'feeding',
    'users':'users', 'roles':'roles', 'role_permissions':'roles',
}
EVENT_MODULES = {1:'health', 2:'health', 3:'health', 4:'weights', 5:'breeding',
                 6:'breeding', 7:'breeding', 8:'exits', 9:'locations'}


def actor_summary(user):
    if user is None:
        return None
    return dict(id=user.id, name=' '.join(filter(None, [user.name, user.middle_name,
                user.paternal_lastname, user.maternal_lastname])), email=user.email, active=user.active)


class SQLAuditRepository:
    def __init__(self, db):
        self.db = db
        self.event_type = case((AuditModel.table == 'events', func.coalesce(
            AuditModel.new_values['event_type_id'].as_integer(),
            AuditModel.old_values['event_type_id'].as_integer(), EventModel.event_type_id)), else_=None)
        self.module = case((AuditModel.table == 'history_rectifications', AuditModel.new_values['module'].as_string()), (AuditModel.table == 'events', case(EVENT_MODULES, value=self.event_type,
            else_='other')), else_=case(TABLE_MODULES, value=AuditModel.table, else_='other'))
        self.record_name = func.coalesce(AuditModel.new_values['name'].as_string(),
            AuditModel.old_values['name'].as_string(), AuditModel.new_values['siniiga'].as_string(),
            AuditModel.old_values['siniiga'].as_string(), AnimalModel.name, AnimalModel.siniiga)

    def query(self, detail=False):
        # List queries never load snapshots; the detail retrieves one sanitized pair.
        columns = [AuditModel.id, AuditModel.date, AuditModel.table, AuditModel.record_id,
                   AuditModel.action, UserModel, self.module.label('module'),
                   self.event_type.label('event_type_id'), self.record_name.label('record_name')]
        if detail:
            columns += [AuditModel.old_values, AuditModel.new_values]
        return select(*columns).outerjoin(UserModel, UserModel.id == AuditModel.user_id).outerjoin(
            EventModel, (AuditModel.table == 'events') & (EventModel.id == AuditModel.record_id)).outerjoin(
            AnimalModel, AnimalModel.id == EventModel.animal_id)

    @staticmethod
    def summary(row):
        audit_id, day, table, record_id, action, user, module, event_type, record_name = row[:9]
        return dict(id=audit_id, date=day.replace(tzinfo=timezone.utc) if day.tzinfo is None else day,
                    table=table, record_id=record_id, action=action, actor=actor_summary(user),
                    module=module, event_type_id=event_type, record_name=record_name)

    def page(self, q, module, action, user_id, date_from, date_before, record_id, table, offset, limit):
        statement = self.query()
        if module:
            statement = statement.where(self.module == module)
        if action:
            statement = statement.where(AuditModel.action == action)
        if user_id:
            statement = statement.where(AuditModel.user_id.is_(None) if user_id == 'system'
                                        else AuditModel.user_id == str(user_id))
        if date_from:
            statement = statement.where(AuditModel.date >= date_from)
        if date_before:
            statement = statement.where(AuditModel.date < date_before)
        if table:
            statement = statement.where(AuditModel.table == table)
        if record_id:
            statement = statement.where(AuditModel.record_id == record_id)
        if q:
            statement = statement.where(or_(self.record_name.icontains(q, autoescape=True),
                AuditModel.record_id.icontains(q, autoescape=True),
                UserModel.name.icontains(q, autoescape=True), UserModel.middle_name.icontains(q, autoescape=True),
                UserModel.paternal_lastname.icontains(q, autoescape=True),
                UserModel.maternal_lastname.icontains(q, autoescape=True), UserModel.email.icontains(q, autoescape=True)))
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.execute(statement.order_by(AuditModel.date.desc(), AuditModel.id.desc()).offset(offset).limit(limit))
        return dict(items=[self.summary(row) for row in rows], total=total, offset=offset, limit=limit)

    def detail(self, audit_id):
        row = self.db.execute(self.query(True).where(AuditModel.id == audit_id)).first()
        if row is None:
            raise ApplicationError('Audit record not found', 404)
        before, after = redact(row[9]), redact(row[10])
        changes = changed_fields(before, after)
        references = {'role_id':RoleModel, 'animal_id':AnimalModel, 'mother_id':AnimalModel,
            'father_id':AnimalModel, 'male_id':AnimalModel, 'group_id':AnimalGroupModel,
            'location_id':LocationModel, 'product_id':ProductModel, 'feed_id':FeedModel,
            'breed_id':BreedModel, 'program_id':HealthProgramModel,
            'unit_id':UnitModel, 'dose_unit_id':UnitModel, 'route_id':AdministrationRouteModel,
            'expense_category_id':ExpenseCategoryModel, 'income_category_id':IncomeCategoryModel,
            'supplier_id':SupplierModel}
        for change in changes:
            model = references.get(change['field'].split('.')[-1])
            if model is None:
                continue
            for side in ('before', 'after'):
                value = change[side]
                if not isinstance(value, (str, int)) or isinstance(value, bool):
                    continue
                reference = self.db.get(model, value)
                if reference:
                    change[side + '_label'] = (reference.code if model is UnitModel else
                        reference.name or getattr(reference, 'siniiga', None))
        return dict(**self.summary(row), old_values=before, new_values=after, changes=changes)

    def users(self, q, limit):
        statement = select(UserModel).where(exists(select(AuditModel.id).where(AuditModel.user_id == UserModel.id)))
        if q:
            statement = statement.where(or_(UserModel.name.icontains(q, autoescape=True),
                UserModel.paternal_lastname.icontains(q, autoescape=True), UserModel.email.icontains(q, autoescape=True)))
        return [actor_summary(user) for user in self.db.scalars(statement.order_by(UserModel.name, UserModel.id).limit(limit))]
