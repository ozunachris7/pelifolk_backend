from src.core.herd import has_exited, ensure_in_herd
from datetime import date, datetime, time, timezone, timedelta
from sqlalchemy import select, func, or_, exists
from src.core.models import AnimalModel, EventModel, EventObservationModel, HealthCaseModel, EventDiagnosisModel, UserModel, AuditModel, ProductModel, UnitModel, ProductTypeModel, AdministrationRouteModel, EventTreatmentModel, HealthProgramModel, ExitModel
from src.core.errors import ApplicationError

class SQLHealthRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def summary(animal):
        return dict(id=animal.id, name=animal.name, siniiga=animal.siniiga)

    @staticmethod
    def user_name(user):
        return ' '.join(filter(None, [user.name, user.middle_name, user.paternal_lastname, user.maternal_lastname])) if user else 'Usuario no disponible'

    def animal(self, animal_id, lock=False):
        statement = select(AnimalModel).where(AnimalModel.id == animal_id)
        animal = self.db.scalar(statement.with_for_update() if lock else statement)
        if not animal:
            raise ApplicationError('Animal not found', 404)
        return animal

    @staticmethod
    def search(statement, q):
        if q:
            statement = statement.where(or_(AnimalModel.name.icontains(q, autoescape=True), AnimalModel.siniiga.icontains(q, autoescape=True)))
        return statement

    def options(self, q, limit):
        return [self.summary(a) for a in self.db.scalars(self.search(select(AnimalModel).where(~has_exited(AnimalModel.id, date.today())), q).order_by(AnimalModel.name, AnimalModel.id).limit(limit))]

    def observation_query(self):
        replacement = select(EventModel.id).where(EventModel.replaced_event_id == EventObservationModel.event_id).correlate(EventObservationModel)
        return select(EventModel, EventObservationModel, AnimalModel, UserModel).join(EventObservationModel, EventObservationModel.event_id == EventModel.id).join(AnimalModel, AnimalModel.id == EventModel.animal_id).join(UserModel, UserModel.id == EventModel.user_id).where(EventModel.event_type_id == 1, ~exists(replacement))

    def observation_response(self, row):
        event, observation, animal, user = row
        return dict(id=event.id, animal=self.summary(animal), date=event.date.date(), observation=observation.observation, recorded_by=self.user_name(user))

    def observations(self, q, offset, limit):
        statement = self.search(self.observation_query(), q)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.execute(statement.order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id).offset(offset).limit(limit))
        return dict(items=[self.observation_response(row) for row in rows], total=total, offset=offset, limit=limit)

    def create_observation(self, data, actor):
        animal = self.animal(str(data.animal_id), True)
        if animal.birth_date and data.date < animal.birth_date:
            raise ApplicationError('Health date is before birth date', 422)
        ensure_in_herd(self.db, animal.id, data.date)
        event = EventModel(animal_id=animal.id, event_type_id=1, date=datetime.combine(data.date, time.min), user_id=actor.id, role_id=actor.role.id)
        self.db.add(event); self.db.flush()
        observation = EventObservationModel(event_id=event.id, event_type_id=1, observation=data.observation)
        self.db.add(observation)
        self.db.add(AuditModel(user_id=actor.id, table='events', record_id=event.id, action='INSERT', new_values=dict(animal_id=animal.id, event_type_id=1, date=data.date.isoformat(), observation=data.observation, role_id=actor.role.id)))
        self.db.flush()
        return self.observation_response((event, observation, animal, self.db.get(UserModel, actor.id)))

    def case_response(self, case, animal):
        return dict(id=case.id, animal=self.summary(animal), reason=case.reason, status=case.status, start_date=case.start_date, closed_date=case.closed_date, notes=case.notes)

    @staticmethod
    def snapshot(case):
        return dict(animal_id=case.animal_id, reason=case.reason, status=case.status, start_date=case.start_date.isoformat(), closed_date=case.closed_date.isoformat() if case.closed_date else None, notes=case.notes)

    def cases(self, q, status, offset, limit):
        statement = self.search(select(HealthCaseModel, AnimalModel).join(AnimalModel, AnimalModel.id == HealthCaseModel.animal_id), q)
        if status:
            statement = statement.where(HealthCaseModel.status == status)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.db.execute(statement.order_by(HealthCaseModel.start_date.desc(), HealthCaseModel.id).offset(offset).limit(limit))
        return dict(items=[self.case_response(c,a) for c,a in rows], total=total, offset=offset, limit=limit)

    def create_case(self, data, actor):
        animal = self.animal(str(data.animal_id), True)
        if animal.birth_date and data.start_date < animal.birth_date:
            raise ApplicationError('Health date is before birth date', 422)
        ensure_in_herd(self.db, animal.id, data.start_date)
        case = HealthCaseModel(animal_id=animal.id, reason=data.reason, start_date=data.start_date, notes=data.notes or None, status='open')
        self.db.add(case);self.db.flush()
        self.db.add(AuditModel(user_id=actor.id, table='health_cases', record_id=case.id, action='INSERT', new_values=self.snapshot(case)))
        self.db.flush()
        return self.case_response(case, animal)

    def case(self, case_id, lock=False):
        statement = select(HealthCaseModel).where(HealthCaseModel.id == case_id)
        case = self.db.scalar(statement.with_for_update() if lock else statement)
        if not case:
            raise ApplicationError('Health case not found', 404)
        return case

    def detail(self, case_id):
        case = self.case(case_id)
        activity = []
        for audit, user in self.db.execute(select(AuditModel, UserModel).outerjoin(UserModel, UserModel.id == AuditModel.user_id).where(AuditModel.table == 'health_cases', AuditModel.record_id == case_id).order_by(AuditModel.date, AuditModel.id)):
            new = audit.new_values or {}
            if new.get('status') not in ('open','under_treatment','closed'):
                continue
            activity.append(dict(date=audit.date.replace(tzinfo=timezone.utc).isoformat(), recorded_by=self.user_name(user), action=audit.action, previous_status=(audit.old_values or {}).get('status'), status=new['status'], closed_date=new.get('closed_date')))
        return dict(case=self.case_response(case, self.animal(case.animal_id)), activity=activity, diagnoses=self.diagnoses(case_id=case_id), treatments=self.treatments(case_id=case_id))

    def change_status(self, case_id, data, actor):
        case = self.case(case_id, True)
        if case.status != data.expected_status:
            raise ApplicationError('Health case changed; reload before updating', 409)
        if data.status == case.status:
            raise ApplicationError('Health case already has this status', 409)
        if data.closed_date and data.closed_date < case.start_date:
            raise ApplicationError('Closed date is before case start date', 422)
        if data.closed_date and self.db.scalar(select(EventModel.id).join(EventDiagnosisModel, EventDiagnosisModel.event_id == EventModel.id).where(EventDiagnosisModel.health_case_id == case_id, EventModel.date >= datetime.combine(data.closed_date, time.max)).limit(1)):
            raise ApplicationError('Closed date is before a diagnosis', 422)
        if data.closed_date and self.db.scalar(select(EventTreatmentModel.event_id).where(EventTreatmentModel.health_case_id == case_id, EventTreatmentModel.end_date > data.closed_date + timedelta(days=1)).limit(1)):
            raise ApplicationError('Closed date is before treatment ends', 422)
        previous = self.snapshot(case)
        case.status, case.closed_date = data.status, data.closed_date
        self.db.add(AuditModel(user_id=actor.id, table='health_cases', record_id=case.id, action='UPDATE', old_values=previous, new_values=self.snapshot(case)))
        self.db.flush()
        return self.case_response(case, self.animal(case.animal_id))

    def history(self, animal_id):
        animal = self.animal(animal_id)
        observations = self.db.execute(self.observation_query().where(EventModel.animal_id == animal_id).order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id))
        cases = self.db.scalars(select(HealthCaseModel).where(HealthCaseModel.animal_id == animal_id).order_by(HealthCaseModel.start_date.desc(), HealthCaseModel.id))
        return dict(animal=self.summary(animal), observations=[self.observation_response(row) for row in observations], cases=[self.case_response(c,animal) for c in cases], diagnoses=self.diagnoses(animal_id=animal_id), treatments=self.treatments(animal_id=animal_id))


    def diagnosis_response(self, event, diagnosis, animal, user):
        return dict(id=event.id, health_case_id=diagnosis.health_case_id, animal=self.summary(animal), date=event.date.date(), diagnosis=diagnosis.diagnosis, severity=diagnosis.severity, recorded_by=self.user_name(user))

    def diagnoses(self, *, case_id=None, animal_id=None):
        replacement = select(EventModel.id).where(EventModel.replaced_event_id == EventDiagnosisModel.event_id).correlate(EventDiagnosisModel)
        statement = select(EventModel, EventDiagnosisModel, AnimalModel, UserModel).join(EventDiagnosisModel, EventDiagnosisModel.event_id == EventModel.id).join(AnimalModel, AnimalModel.id == EventModel.animal_id).join(UserModel, UserModel.id == EventModel.user_id).where(EventModel.event_type_id == 2, ~exists(replacement))
        if case_id:
            statement = statement.where(EventDiagnosisModel.health_case_id == case_id)
        if animal_id:
            statement = statement.where(EventModel.animal_id == animal_id)
        return [self.diagnosis_response(*row) for row in self.db.execute(statement.order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id))]

    def create_diagnosis(self, case_id, data, actor):
        # Lock animal before case, matching animal birth-date editing lock order.
        reference = self.case(case_id)
        animal = self.animal(reference.animal_id, True)
        ensure_in_herd(self.db, animal.id, data.date)
        self.db.expire(reference)
        case = self.case(case_id, True)
        if case.status == 'closed':
            raise ApplicationError('Reopen the case before adding a diagnosis', 409)
        if data.date < case.start_date:
            raise ApplicationError('Diagnosis date is before case start date', 422)
        if animal.birth_date and data.date < animal.birth_date:
            raise ApplicationError('Health date is before birth date', 422)
        event = EventModel(animal_id=animal.id, event_type_id=2, date=datetime.combine(data.date, time.min), user_id=actor.id, role_id=actor.role.id)
        self.db.add(event);self.db.flush()
        diagnosis = EventDiagnosisModel(event_id=event.id, event_type_id=2, health_case_id=case.id, diagnosis=data.diagnosis, severity=data.severity)
        self.db.add(diagnosis)
        self.db.add(AuditModel(user_id=actor.id, table='events', record_id=event.id, action='INSERT', new_values=dict(animal_id=animal.id, event_type_id=2, health_case_id=case.id, date=data.date.isoformat(), diagnosis=data.diagnosis, severity=data.severity, role_id=actor.role.id)))
        self.db.flush()
        return self.diagnosis_response(event, diagnosis, animal, self.db.get(UserModel, actor.id))


    def catalogs(self):
        return dict(product_types=[dict(id=p.id,name=p.name) for p in self.db.scalars(select(ProductTypeModel).order_by(ProductTypeModel.name))], units=[dict(id=u.id,code=u.code) for u in self.db.scalars(select(UnitModel).order_by(UnitModel.code))], routes=[dict(id=r.id,name=r.name) for r in self.db.scalars(select(AdministrationRouteModel).order_by(AdministrationRouteModel.name))])

    def product_response(self, product):
        return dict(id=product.id, name=product.name, product_type_id=product.product_type_id, product_type_name=self.db.get(ProductTypeModel, product.product_type_id).name, unit_id=product.unit_id, unit_code=self.db.get(UnitModel, product.unit_id).code, withdrawal_days=product.withdrawal_days, active=product.active)

    def products(self, q, active, offset, limit):
        statement=select(ProductModel)
        if q:
            statement=statement.where(ProductModel.name.icontains(q, autoescape=True))
        if active is not None:
            statement=statement.where(ProductModel.active == active)
        total=self.db.scalar(select(func.count()).select_from(statement.subquery()))
        return dict(items=[self.product_response(p) for p in self.db.scalars(statement.order_by(ProductModel.name, ProductModel.id).offset(offset).limit(limit))],total=total,offset=offset,limit=limit)

    def save_product(self, data, actor, product_id=None):
        product=None
        if product_id:
            product=self.db.scalar(select(ProductModel).where(ProductModel.id == product_id).with_for_update())
            if not product:
                raise ApplicationError('Product not found', 404)
        if self.db.scalar(select(ProductModel.id).where(func.lower(ProductModel.name)==data.name.lower(), ProductModel.id != product_id if product_id else True)):
            raise ApplicationError('Product name already exists',409)
        if not self.db.get(ProductTypeModel, data.product_type_id) or not self.db.get(UnitModel,data.unit_id):
            raise ApplicationError('Product catalog entry not found',422)
        previous=self.product_response(product) if product else None
        if not product:
            product=ProductModel();self.db.add(product)
        for name,value in data.model_dump().items():
            setattr(product,name,value)
        self.db.flush()
        self.db.add(AuditModel(user_id=actor.id,table='products',record_id=product.id,action='UPDATE' if previous else 'INSERT',old_values=previous,new_values=self.product_response(product)))
        self.db.flush()
        return self.product_response(product)

    def treatment_response(self, event, treatment, animal, user):
        return dict(id=event.id,health_case_id=treatment.health_case_id,program_id=treatment.program_id,program_name=self.db.get(HealthProgramModel,treatment.program_id).name if treatment.program_id else None,animal=self.summary(animal),product=self.product_response(self.db.get(ProductModel,treatment.product_id)),start_date=treatment.start_date,end_date=treatment.end_date,last_day=treatment.end_date-timedelta(days=1),dose_value=treatment.dose_value,dose_unit_id=treatment.dose_unit_id,dose_unit_code=self.db.get(UnitModel,treatment.dose_unit_id).code,route_id=treatment.route_id,route_name=self.db.get(AdministrationRouteModel,treatment.route_id).name,frequency_hours=treatment.frequency_hours,duration_days=treatment.duration_days,recorded_by=self.user_name(user))

    def treatments(self, *, case_id=None, animal_id=None):
        replacement=select(EventModel.id).where(EventModel.replaced_event_id == EventTreatmentModel.event_id).correlate(EventTreatmentModel)
        statement=select(EventModel,EventTreatmentModel,AnimalModel,UserModel).join(EventTreatmentModel,EventTreatmentModel.event_id==EventModel.id).join(AnimalModel,AnimalModel.id==EventModel.animal_id).join(UserModel,UserModel.id==EventModel.user_id).where(EventModel.event_type_id==3,~exists(replacement))
        if case_id:
            statement=statement.where(EventTreatmentModel.health_case_id==case_id)
        if animal_id:
            statement=statement.where(EventModel.animal_id==animal_id)
        return [self.treatment_response(*row) for row in self.db.execute(statement.order_by(EventModel.date.desc(),EventModel.created_at.desc(),EventModel.id,EventTreatmentModel.product_id))]

    def create_treatment(self, case_id, data, actor):
        reference=self.case(case_id)
        animal=self.animal(reference.animal_id,True)
        ensure_in_herd(self.db, animal.id, data.start_date + timedelta(days=data.duration_days - 1))
        self.db.expire(reference)
        case=self.case(case_id,True)
        if case.status=='closed':
            raise ApplicationError('Reopen the case before adding a treatment',409)
        if data.start_date < case.start_date:
            raise ApplicationError('Treatment date is before case start date',422)
        if animal.birth_date and data.start_date < animal.birth_date:
            raise ApplicationError('Health date is before birth date',422)
        product=self.db.scalar(select(ProductModel).where(ProductModel.id==str(data.product_id)).with_for_update())
        if not product:
            raise ApplicationError('Product not found',404)
        if not product.active:
            raise ApplicationError('Product is inactive',409)
        if not self.db.get(UnitModel,data.dose_unit_id) or not self.db.get(AdministrationRouteModel,data.route_id):
            raise ApplicationError('Treatment catalog entry not found',422)
        event=EventModel(animal_id=animal.id,event_type_id=3,date=datetime.combine(data.start_date,time.min),user_id=actor.id,role_id=actor.role.id)
        self.db.add(event);self.db.flush()
        treatment=EventTreatmentModel(event_id=event.id,event_type_id=3,health_case_id=case.id,**data.model_dump(mode='python',exclude={'product_id'}),product_id=str(data.product_id))
        self.db.add(treatment)
        self.db.add(AuditModel(user_id=actor.id,table='events',record_id=event.id,action='INSERT',new_values=dict(animal_id=animal.id,event_type_id=3,health_case_id=case.id,role_id=actor.role.id,**data.model_dump(mode='json'))))
        if case.status=='open':
            previous=self.snapshot(case);case.status='under_treatment'
            self.db.add(AuditModel(user_id=actor.id,table='health_cases',record_id=case.id,action='UPDATE',old_values=previous,new_values=self.snapshot(case)))
        self.db.flush();self.db.refresh(treatment)
        return self.treatment_response(event,treatment,animal,self.db.get(UserModel,actor.id))
