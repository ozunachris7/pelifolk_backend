from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import Boolean, Computed, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class RoleModel(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    permissions: Mapped[list["RolePermissionModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin")


class RolePermissionModel(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission: Mapped[str] = mapped_column(String(80), primary_key=True)


class UserModel(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    middle_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    paternal_lastname: Mapped[str] = mapped_column(String(120))
    maternal_lastname: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(190), unique=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"))
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    role: Mapped[RoleModel] = relationship(lazy="selectin")


class AuditModel(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    table: Mapped[str] = mapped_column("table_name", String(64))
    record_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(6))
    old_values: Mapped[dict | None] = mapped_column(JSON)
    new_values: Mapped[dict | None] = mapped_column(JSON)
    date: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class BreedModel(Base):
    __tablename__ = "breeds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class AnimalModel(Base):
    __tablename__ = "animals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    siniiga: Mapped[str | None] = mapped_column(String(30), unique=True)
    name: Mapped[str | None] = mapped_column(String(100))
    sex: Mapped[str] = mapped_column(String(6))
    birth_date: Mapped[date | None] = mapped_column(Date)
    origin: Mapped[str] = mapped_column(String(20), default="born_in_herd")
    mother_id: Mapped[str | None] = mapped_column(ForeignKey("animals.id"))
    father_id: Mapped[str | None] = mapped_column(ForeignKey("animals.id"))
    is_breeder: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    breeds: Mapped[list["AnimalBreedModel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin")


class AnimalBreedModel(Base):
    __tablename__ = "animal_breeds"
    animal_id: Mapped[str] = mapped_column(ForeignKey("animals.id"), primary_key=True)
    breed_id: Mapped[int] = mapped_column(ForeignKey("breeds.id"), primary_key=True)
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    breed: Mapped[BreedModel] = relationship(lazy="joined")


class LocationTypeModel(Base):
    __tablename__ = 'location_types'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class LocationModel(Base):
    __tablename__ = 'locations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    location_type_id: Mapped[int] = mapped_column(ForeignKey('location_types.id'))
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    location_type: Mapped[LocationTypeModel] = relationship(lazy='joined')


class AnimalGroupModel(Base):
    __tablename__ = 'animal_groups'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class GroupAnimalModel(Base):
    __tablename__ = 'group_animals'
    __table_args__ = (CheckConstraint('end_date IS NULL OR end_date >= start_date'),)
    group_id: Mapped[str] = mapped_column(ForeignKey('animal_groups.id'), primary_key=True)
    animal_id: Mapped[str] = mapped_column(ForeignKey('animals.id'), primary_key=True)
    start_date: Mapped[date] = mapped_column(Date, primary_key=True)
    end_date: Mapped[date | None] = mapped_column(Date)


class EventTypeModel(Base):
    __tablename__ = 'event_types'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(80))


class EventModel(Base):
    __tablename__ = 'events'
    __table_args__ = (UniqueConstraint('id', 'event_type_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    animal_id: Mapped[str] = mapped_column(ForeignKey('animals.id'))
    event_type_id: Mapped[int] = mapped_column(ForeignKey('event_types.id'))
    date: Mapped[datetime] = mapped_column(DateTime)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    role_id: Mapped[str] = mapped_column(ForeignKey('roles.id'))
    location_id: Mapped[str | None] = mapped_column(ForeignKey('locations.id'))
    reason: Mapped[str | None] = mapped_column(Text)
    replaced_event_id: Mapped[str | None] = mapped_column(ForeignKey('events.id'), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class EventWeightModel(Base):
    __tablename__ = 'event_weights'
    __table_args__ = (ForeignKeyConstraint(['event_id', 'event_type_id'], ['events.id', 'events.event_type_id']), CheckConstraint('event_type_id = 4'), CheckConstraint('weight_kg > 0'))
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type_id: Mapped[int] = mapped_column(Integer, default=4)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(7, 2))


class HealthCaseModel(Base):
    __tablename__ = 'health_cases'
    __table_args__ = (CheckConstraint("(status = 'closed' AND closed_date IS NOT NULL) OR (status <> 'closed' AND closed_date IS NULL)"), CheckConstraint('closed_date IS NULL OR closed_date >= start_date'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    animal_id: Mapped[str] = mapped_column(ForeignKey('animals.id'))
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default='open')
    start_date: Mapped[date] = mapped_column(Date)
    closed_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class EventObservationModel(Base):
    __tablename__ = 'event_observations'
    __table_args__ = (ForeignKeyConstraint(['event_id', 'event_type_id'], ['events.id', 'events.event_type_id']), CheckConstraint('event_type_id = 1'),)
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type_id: Mapped[int] = mapped_column(Integer, default=1)
    observation: Mapped[str] = mapped_column(Text)


class EventDiagnosisModel(Base):
    __tablename__ = 'event_diagnoses'
    __table_args__ = (ForeignKeyConstraint(['event_id', 'event_type_id'], ['events.id', 'events.event_type_id']), CheckConstraint('event_type_id = 2'),)
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type_id: Mapped[int] = mapped_column(Integer, default=2)
    health_case_id: Mapped[str] = mapped_column(ForeignKey('health_cases.id'))
    diagnosis: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10))


class UnitModel(Base):
    __tablename__ = 'units'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)


class ProductTypeModel(Base):
    __tablename__ = 'product_types'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class AdministrationRouteModel(Base):
    __tablename__ = 'administration_routes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class ProductModel(Base):
    __tablename__ = 'products'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    product_type_id: Mapped[int] = mapped_column(ForeignKey('product_types.id'))
    unit_id: Mapped[int] = mapped_column(ForeignKey('units.id'))
    withdrawal_days: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


from sqlalchemy.sql.expression import ColumnElement
from sqlalchemy.ext.compiler import compiles

class TreatmentEnd(ColumnElement):
    inherit_cache = True

@compiles(TreatmentEnd, 'mysql')
def treatment_end_mysql(element, compiler, **kw):
    return 'DATE_ADD(start_date, INTERVAL duration_days DAY)'

@compiles(TreatmentEnd, 'sqlite')
def treatment_end_sqlite(element, compiler, **kw):
    return "date(start_date, '+' || duration_days || ' days')"


class EventTreatmentModel(Base):
    __tablename__ = 'event_treatments'
    __table_args__ = (ForeignKeyConstraint(['event_id', 'event_type_id'], ['events.id', 'events.event_type_id']), CheckConstraint('event_type_id = 3'), CheckConstraint('dose_value > 0'), CheckConstraint('duration_days > 0'), CheckConstraint('frequency_hours IS NULL OR frequency_hours > 0'),)
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), primary_key=True)
    event_type_id: Mapped[int] = mapped_column(Integer, default=3)
    health_case_id: Mapped[str | None] = mapped_column(ForeignKey('health_cases.id'))
    program_id: Mapped[str | None] = mapped_column(ForeignKey('health_programs.id'))
    dose_value: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    dose_unit_id: Mapped[int] = mapped_column(ForeignKey('units.id'))
    route_id: Mapped[int] = mapped_column(ForeignKey('administration_routes.id'))
    frequency_hours: Mapped[int | None] = mapped_column(Integer)
    duration_days: Mapped[int] = mapped_column(Integer, default=1)
    start_date: Mapped[date] = mapped_column(Date)
    withdrawal_days: Mapped[int | None] = mapped_column(Integer)
    end_date: Mapped[date] = mapped_column(Date, Computed(TreatmentEnd(), persisted=True))


class HealthProgramModel(Base):
    __tablename__ = 'health_programs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'))
    interval_days: Mapped[int] = mapped_column(Integer)
    minimum_age_days: Mapped[int] = mapped_column(Integer, default=0)
    sex: Mapped[str | None] = mapped_column(String(6))
    notice_days: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExitModel(Base):
    __tablename__ = 'exits'
    __table_args__ = (ForeignKeyConstraint(['event_id','event_type_id'],['events.id','events.event_type_id']),)
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type_id: Mapped[int] = mapped_column(Integer, default=8)
    exit_type: Mapped[str] = mapped_column(String(10))


class BirthTypeModel(Base):
    __tablename__ = 'birth_types'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)

class EventMatingModel(Base):
    __tablename__ = 'event_matings'
    __table_args__ = (ForeignKeyConstraint(['event_id','event_type_id'],['events.id','events.event_type_id']),CheckConstraint('event_type_id = 5'),)
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type_id: Mapped[int] = mapped_column(Integer, default=5)
    male_id: Mapped[str] = mapped_column(ForeignKey('animals.id'))
    kinship_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

class EventPregnancyModel(Base):
    __tablename__ = 'event_pregnancy_diagnoses'
    __table_args__ = (ForeignKeyConstraint(['event_id','event_type_id'],['events.id','events.event_type_id']),CheckConstraint('event_type_id = 6'),)
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type_id: Mapped[int] = mapped_column(Integer, default=6)
    result: Mapped[str] = mapped_column(String(12))
    mating_event_id: Mapped[str | None] = mapped_column(ForeignKey('event_matings.event_id'))

class EventBirthModel(Base):
    __tablename__ = 'event_births'
    __table_args__ = (ForeignKeyConstraint(['event_id','event_type_id'],['events.id','events.event_type_id']),CheckConstraint('event_type_id = 7'),)
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type_id: Mapped[int] = mapped_column(Integer, default=7)
    birth_type_id: Mapped[int] = mapped_column(ForeignKey('birth_types.id'))
    notes: Mapped[str | None] = mapped_column(Text)

class BirthOffspringModel(Base):
    __tablename__ = 'event_birth_offspring'
    animal_id: Mapped[str] = mapped_column(ForeignKey('animals.id'), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey('event_births.event_id'))
    alive: Mapped[bool] = mapped_column(Boolean, default=True)
    birth_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5,2))


class ExpenseCategoryModel(Base):
    __tablename__ = 'expense_categories'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class IncomeCategoryModel(Base):
    __tablename__ = 'income_categories'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class SupplierModel(Base):
    __tablename__ = 'suppliers'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(190))
    address: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExpenseModel(Base):
    __tablename__ = 'expenses'
    __table_args__ = (CheckConstraint('amount > 0'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    supplier_id: Mapped[str | None] = mapped_column(ForeignKey('suppliers.id'))
    expense_category_id: Mapped[int] = mapped_column(ForeignKey('expense_categories.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    date: Mapped[date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)


class IncomeModel(Base):
    __tablename__ = 'incomes'
    __table_args__ = (CheckConstraint('amount >= 0'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    income_category_id: Mapped[int] = mapped_column(ForeignKey('income_categories.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    date: Mapped[date] = mapped_column(Date)
    exit_event_id: Mapped[str | None] = mapped_column(ForeignKey('exits.event_id'), unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class FeedModel(Base):
    __tablename__ = 'feeds'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey('units.id'))


class FeedPriceModel(Base):
    __tablename__ = 'feed_prices'
    __table_args__ = (CheckConstraint('unit_cost >= 0'),)
    feed_id: Mapped[str] = mapped_column(ForeignKey('feeds.id'), primary_key=True)
    effective_from: Mapped[date] = mapped_column(Date, primary_key=True)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12,4))


class FeedingModel(Base):
    __tablename__ = 'feedings'
    __table_args__ = (CheckConstraint('quantity > 0'), CheckConstraint('(animal_id IS NOT NULL) + (group_id IS NOT NULL) = 1'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    animal_id: Mapped[str | None] = mapped_column(ForeignKey('animals.id'))
    group_id: Mapped[str | None] = mapped_column(ForeignKey('animal_groups.id'))
    date: Mapped[date] = mapped_column(Date)
    feed_id: Mapped[str] = mapped_column(ForeignKey('feeds.id'))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10,2))


class ExpenseAllocationModel(Base):
    __tablename__ = 'expense_allocations'
    __table_args__ = (
        CheckConstraint('percentage > 0 AND percentage <= 100'),
        CheckConstraint('(animal_id IS NOT NULL) + (group_id IS NOT NULL) + (health_case_id IS NOT NULL) = 1'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    expense_id: Mapped[str] = mapped_column(ForeignKey('expenses.id', ondelete='CASCADE'))
    animal_id: Mapped[str | None] = mapped_column(ForeignKey('animals.id'))
    group_id: Mapped[str | None] = mapped_column(ForeignKey('animal_groups.id'))
    health_case_id: Mapped[str | None] = mapped_column(ForeignKey('health_cases.id'))
    percentage: Mapped[Decimal] = mapped_column(Numeric(5,2), default=100)


class CaseFollowupModel(Base):
    __tablename__ = 'health_case_followups'
    __table_args__ = (CheckConstraint('next_review_date IS NULL OR next_review_date >= date'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    health_case_id: Mapped[str] = mapped_column(ForeignKey('health_cases.id'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    role_id: Mapped[str] = mapped_column(ForeignKey('roles.id'))
    evolution: Mapped[str] = mapped_column(String(20))
    treatment_result: Mapped[str] = mapped_column(String(25))
    notes: Mapped[str] = mapped_column(Text)
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    date: Mapped[date] = mapped_column(Date)


class AnimalDecisionModel(Base):
    __tablename__ = 'animal_decisions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    animal_id: Mapped[str] = mapped_column(ForeignKey('animals.id'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    role_id: Mapped[str] = mapped_column(ForeignKey('roles.id'))
    kind: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    date: Mapped[date] = mapped_column(Date)


class EventWeaningModel(Base):
    __tablename__ = 'event_weanings'
    event_id: Mapped[str] = mapped_column(ForeignKey('event_weights.event_id'), primary_key=True)
    animal_id: Mapped[str] = mapped_column(ForeignKey('animals.id'), unique=True)
    mother_id: Mapped[str | None] = mapped_column(ForeignKey('animals.id'), nullable=True)
    birth_date_snapshot: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    role_id: Mapped[str] = mapped_column(ForeignKey('roles.id'))
