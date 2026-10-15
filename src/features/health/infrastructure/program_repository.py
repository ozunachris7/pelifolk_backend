from src.core.herd import ensure_in_herd
from datetime import date, datetime, time, timedelta
from sqlalchemy import select,func,exists
from sqlalchemy.orm import aliased
from src.core.models import HealthProgramModel,ProductModel,AnimalModel,EventModel,EventTreatmentModel,ExitModel,UnitModel,AdministrationRouteModel,AuditModel,UserModel
from src.core.errors import ApplicationError
from src.features.health.domain.schedule import next_application
from .repository import SQLHealthRepository

class SQLProgramRepository(SQLHealthRepository):
    def program(self, program_id, lock=False):
        statement=select(HealthProgramModel).where(HealthProgramModel.id==program_id)
        p=self.db.scalar(statement.with_for_update() if lock else statement)
        if not p:
            raise ApplicationError('Health program not found',404)
        return p

    def program_response(self,p):
        return dict(id=p.id,name=p.name,product=self.product_response(self.db.get(ProductModel,p.product_id)),interval_days=p.interval_days,minimum_age_days=p.minimum_age_days,sex=p.sex,notice_days=p.notice_days,active=p.active)

    def programs(self,q,active,offset,limit):
        statement=select(HealthProgramModel)
        if q:
            statement=statement.where(HealthProgramModel.name.icontains(q,autoescape=True))
        if active is not None:
            statement=statement.where(HealthProgramModel.active==active)
        total=self.db.scalar(select(func.count()).select_from(statement.subquery()))
        return dict(items=[self.program_response(p) for p in self.db.scalars(statement.order_by(HealthProgramModel.name,HealthProgramModel.id).offset(offset).limit(limit))],total=total,offset=offset,limit=limit)

    def save_program(self,data,actor,program_id=None):
        p=self.program(program_id,True) if program_id else None
        if self.db.scalar(select(HealthProgramModel.id).where(func.lower(HealthProgramModel.name)==data.name.lower(),HealthProgramModel.id!=program_id if program_id else True)):
            raise ApplicationError('Health program name already exists',409)
        product=self.db.scalar(select(ProductModel).where(ProductModel.id==str(data.product_id)).with_for_update())
        if not product:
            raise ApplicationError('Product not found',404)
        if data.active and not product.active:
            raise ApplicationError('Product is inactive',409)
        if p and p.product_id!=str(data.product_id) and self.db.scalar(select(EventTreatmentModel.event_id).where(EventTreatmentModel.program_id==p.id).limit(1)):
            raise ApplicationError('Cannot change product of a program with applications',409)
        previous=self.program_response(p) if p else None
        if p is None:
            p=HealthProgramModel();self.db.add(p)
        for name,value in data.model_dump(mode='python').items():
            setattr(p,name,str(value) if name=='product_id' else value)
        self.db.flush()
        self.db.add(AuditModel(user_id=actor.id,table='health_programs',record_id=p.id,action='UPDATE' if previous else 'INSERT',old_values=previous,new_values=self.program_response(p)))
        self.db.flush()
        return self.program_response(p)

    def effective_exit(self,animal_id,as_of):
        replacement=aliased(EventModel)
        return exists(select(EventModel.id).join(ExitModel,ExitModel.event_id==EventModel.id).where(EventModel.animal_id==animal_id,EventModel.date<datetime.combine(as_of,time.max),~exists(select(replacement.id).where(replacement.replaced_event_id==EventModel.id))))

    def last_applications(self,program_id,animal_id=None):
        replacement=aliased(EventModel)
        statement=select(EventModel.animal_id,func.max(EventTreatmentModel.start_date)).join(EventTreatmentModel,EventTreatmentModel.event_id==EventModel.id).where(EventTreatmentModel.program_id==program_id,EventModel.event_type_id==3,~exists(select(replacement.id).where(replacement.replaced_event_id==EventModel.id)))
        if animal_id:
            statement=statement.where(EventModel.animal_id==animal_id)
        return dict(self.db.execute(statement.group_by(EventModel.animal_id)).all())

    def schedule(self,program_id,q,state,offset,limit):
        p=self.program(program_id);today=date.today();product=self.db.get(ProductModel,p.product_id)
        statement=self.search(select(AnimalModel),q).where(~self.effective_exit(AnimalModel.id,today))
        if p.sex:
            statement=statement.where(AnimalModel.sex==p.sex)
        last=self.last_applications(p.id);items=[]
        for a in self.db.scalars(statement):
            due,remaining,status=next_application(a.birth_date,p.minimum_age_days,last.get(a.id),p.interval_days,p.notice_days,today)
            if state=='attention' and status=='scheduled' or state not in ('all','attention') and status!=state:
                continue
            eligible=not p.minimum_age_days or a.birth_date is not None and (today-a.birth_date).days>=p.minimum_age_days
            items.append(dict(animal=self.summary(a),birth_date=a.birth_date,last_application=last.get(a.id),due_date=due,days_remaining=remaining,status=status,can_apply=p.active and product.active and eligible))
        ranks={'overdue':0,'due':1,'upcoming':2,'missing_birth_date':3,'scheduled':4}
        items.sort(key=lambda item:(ranks[item['status']],item['due_date'] or date.max,(item['animal']['name'] or '').lower(),item['animal']['id']))
        return dict(program=self.program_response(p),as_of=today,items=items[offset:offset+limit],total=len(items),offset=offset,limit=limit)

    def apply_program(self,program_id,data,actor):
        animal=self.animal(str(data.animal_id),True)
        ensure_in_herd(self.db, animal.id, data.start_date + timedelta(days=data.duration_days))
        p=self.program(program_id,True)
        if not p.active:
            raise ApplicationError('Health program is inactive',409)
        if p.sex and animal.sex!=p.sex:
            raise ApplicationError('Animal sex does not match health program',422)
        if animal.birth_date and data.start_date<animal.birth_date:
            raise ApplicationError('Health date is before birth date',422)
        if p.minimum_age_days and (animal.birth_date is None or (data.start_date-animal.birth_date).days<p.minimum_age_days):
            raise ApplicationError('Animal has not reached program minimum age',422)
        if self.db.scalar(select(AnimalModel.id).where(AnimalModel.id==animal.id,self.effective_exit(AnimalModel.id,data.start_date))):
            raise ApplicationError('Animal has left the herd',409)
        last=self.last_applications(p.id,animal.id).get(animal.id)
        if last and data.start_date<=last:
            raise ApplicationError('Application date must be after last program application',409)
        product=self.db.scalar(select(ProductModel).where(ProductModel.id==p.product_id).with_for_update())
        if not product.active:
            raise ApplicationError('Product is inactive',409)
        if not self.db.get(UnitModel,data.dose_unit_id) or not self.db.get(AdministrationRouteModel,data.route_id):
            raise ApplicationError('Treatment catalog entry not found',422)
        event=EventModel(animal_id=animal.id,event_type_id=3,date=datetime.combine(data.start_date,time.min),user_id=actor.id,role_id=actor.role.id)
        self.db.add(event);self.db.flush()
        treatment=EventTreatmentModel(event_id=event.id,event_type_id=3,withdrawal_days=product.withdrawal_days,program_id=p.id,product_id=p.product_id,**data.model_dump(mode='python',exclude={'animal_id'}))
        self.db.add(treatment)
        self.db.add(AuditModel(user_id=actor.id,table='events',record_id=event.id,action='INSERT',new_values=dict(withdrawal_days=product.withdrawal_days,event_type_id=3,program_id=p.id,product_id=p.product_id,role_id=actor.role.id,**data.model_dump(mode='json'))))
        self.db.flush();self.db.refresh(treatment)
        return self.treatment_response(event,treatment,animal,self.db.get(UserModel,actor.id))
