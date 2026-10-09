from src.core.herd import ensure_in_herd
from datetime import timedelta
from datetime import datetime,time
from sqlalchemy import select,func,or_,exists
from sqlalchemy.orm import aliased
from src.core.models import AnimalModel,EventModel,EventMatingModel,EventPregnancyModel,EventBirthModel,BirthOffspringModel,BirthTypeModel,ExitModel,UserModel,AuditModel
from src.core.errors import ApplicationError

class SQLBreedingRepository:
    def __init__(self,db):self.db=db
    @staticmethod
    def summary(a):return dict(id=a.id,name=a.name,siniiga=a.siniiga,sex=a.sex)
    def animal(self,id):
        a=self.db.get(AnimalModel,id)
        if not a:raise ApplicationError('Animal not found',404)
        return a
    def exited(self,id,day):
        replacement=aliased(EventModel)
        return exists(select(EventModel.id).join(ExitModel,ExitModel.event_id==EventModel.id).where(EventModel.animal_id==id,EventModel.date<=datetime.combine(day,time.max),~exists(select(replacement.id).where(replacement.replaced_event_id==EventModel.id))))
    def options(self,q,sex):
        from datetime import date
        statement=select(AnimalModel).where(~self.exited(AnimalModel.id,date.today()))
        if sex:statement=statement.where(AnimalModel.sex==sex)
        if q:statement=statement.where(or_(AnimalModel.name.icontains(q,autoescape=True),AnimalModel.siniiga.icontains(q,autoescape=True)))
        return [self.summary(a) for a in self.db.scalars(statement.order_by(AnimalModel.name,AnimalModel.id).limit(100))]
    def lock_animals(self,ids):
        rows=self.db.scalars(select(AnimalModel).where(AnimalModel.id.in_(ids)).order_by(AnimalModel.id).with_for_update()).all()
        if len(rows)!=len(set(ids)):raise ApplicationError('Animal not found',404)
        return {a.id:a for a in rows}
    def validate(self,a,sex,day):
        ensure_in_herd(self.db, a.id, day + timedelta(days=1))
        if a.sex!=sex:raise ApplicationError('Reproductive animal sex is incompatible',422)
        if a.birth_date and a.birth_date>=day:raise ApplicationError('Reproductive event must be after animal birth',422)
        if self.db.scalar(select(AnimalModel.id).where(AnimalModel.id==a.id,self.exited(AnimalModel.id,day))):raise ApplicationError('Animal has left the herd',409)
    def response(self,e):
        a=self.animal(e.animal_id);u=self.db.get(UserModel,e.user_id)
        result=dict(id=e.id,animal=self.summary(a),date=e.date.date(),notes=e.reason,recorded_by=' '.join(filter(None,[u.name,u.middle_name,u.paternal_lastname,u.maternal_lastname])))
        if e.event_type_id==5:
            m=self.db.get(EventMatingModel,e.id);return dict(**result,kind='mating',male=self.summary(self.animal(m.male_id)))
        if e.event_type_id==6:
            p=self.db.get(EventPregnancyModel,e.id);return dict(**result,kind='pregnancy',result=p.result,mating_event_id=p.mating_event_id)
        b=self.db.get(EventBirthModel,e.id)
        children=[dict(animal=self.summary(self.animal(c.animal_id)),alive=c.alive,birth_weight_kg=c.birth_weight_kg) for c in self.db.scalars(select(BirthOffspringModel).where(BirthOffspringModel.event_id==e.id).order_by(BirthOffspringModel.animal_id))]
        return dict(**result,kind='birth',birth_type=self.db.get(BirthTypeModel,b.birth_type_id).name,offspring=children)
    def query(self):
        replacement=aliased(EventModel)
        return select(EventModel).where(EventModel.event_type_id.in_([5,6,7]),~exists(select(replacement.id).where(replacement.replaced_event_id==EventModel.id)))
    def page(self,kind,q,offset,limit,animal_id=None):
        statement=self.query().join(AnimalModel,AnimalModel.id==EventModel.animal_id)
        if kind:statement=statement.where(EventModel.event_type_id=={'mating':5,'pregnancy':6,'birth':7}[kind])
        if animal_id:statement=statement.where(EventModel.animal_id==animal_id)
        if q:statement=statement.where(or_(AnimalModel.name.icontains(q,autoescape=True),AnimalModel.siniiga.icontains(q,autoescape=True)))
        total=self.db.scalar(select(func.count()).select_from(statement.subquery()))
        return dict(items=[self.response(e) for e in self.db.scalars(statement.order_by(EventModel.date.desc(),EventModel.created_at.desc(),EventModel.id).offset(offset).limit(limit))],total=total,offset=offset,limit=limit)
    def history(self,id):
        a=self.animal(id)
        statement=self.query().outerjoin(EventMatingModel,EventMatingModel.event_id==EventModel.id).where(or_(EventModel.animal_id==id,EventMatingModel.male_id==id,exists(select(BirthOffspringModel.animal_id).where(BirthOffspringModel.event_id==EventModel.id,BirthOffspringModel.animal_id==id))))
        return dict(animal=self.summary(a),items=[self.response(e) for e in self.db.scalars(statement.order_by(EventModel.date.desc(),EventModel.created_at.desc(),EventModel.id))])
    def create(self,kind,data,actor):
        ids=[str(data.animal_id)]
        if kind=='mating':ids.append(str(data.male_id))
        if kind=='birth' and data.father_id:ids.append(str(data.father_id))
        animals=self.lock_animals(ids);mother=animals[str(data.animal_id)];self.validate(mother,'female',data.date)
        father=animals.get(str(data.male_id if kind=='mating' else data.father_id)) if kind in ('mating','birth') else None
        if father:self.validate(father,'male',data.date)
        day=datetime.combine(data.date,time.min)
        if kind=='pregnancy' and data.mating_event_id:
            mating=self.db.get(EventMatingModel,str(data.mating_event_id));event=self.db.get(EventModel,str(data.mating_event_id))
            if not mating or event.animal_id!=mother.id:raise ApplicationError('Mating does not belong to this female',422)
            if event.date.date()>data.date:raise ApplicationError('Pregnancy diagnosis is before mating',422)
        if kind=='birth':
            if not self.db.get(BirthTypeModel,data.birth_type_id):raise ApplicationError('Birth type not found',422)
            if self.db.scalar(select(EventModel.id).where(EventModel.animal_id==mother.id,EventModel.event_type_id==7,EventModel.date>=day,EventModel.date<=datetime.combine(data.date,time.max))):raise ApplicationError('Female already has a birth on this date',409)
            tags=[o.siniiga.lower() for o in data.offspring if o.siniiga]
            if tags and self.db.scalar(select(AnimalModel.id).where(func.lower(AnimalModel.siniiga).in_(tags)).limit(1)):raise ApplicationError('SINIIGA already exists',409)
        event=EventModel(animal_id=mother.id,event_type_id={'mating':5,'pregnancy':6,'birth':7}[kind],date=day,user_id=actor.id,role_id=actor.role.id,reason=data.notes or None);self.db.add(event);self.db.flush()
        if kind=='mating':self.db.add(EventMatingModel(event_id=event.id,event_type_id=5,male_id=father.id))
        elif kind=='pregnancy':self.db.add(EventPregnancyModel(event_id=event.id,event_type_id=6,result=data.result,mating_event_id=str(data.mating_event_id) if data.mating_event_id else None))
        else:
            self.db.add(EventBirthModel(event_id=event.id,event_type_id=7,birth_type_id=data.birth_type_id,notes=data.notes or None));self.db.flush()
            for child in data.offspring:
                a=AnimalModel(name=child.name or None,siniiga=child.siniiga or None,sex=child.sex,birth_date=data.date,origin='born_in_herd',mother_id=mother.id,father_id=father.id if father else None,is_breeder=False);self.db.add(a);self.db.flush()
                self.db.add(BirthOffspringModel(animal_id=a.id,event_id=event.id,alive=child.alive,birth_weight_kg=child.birth_weight_kg))
                self.db.add(AuditModel(user_id=actor.id,table='animals',record_id=a.id,action='INSERT',new_values=dict(name=a.name,siniiga=a.siniiga,sex=a.sex,birth_date=data.date.isoformat(),origin=a.origin,mother_id=mother.id,father_id=a.father_id)))
                if not child.alive:
                    death=EventModel(animal_id=a.id,event_type_id=8,date=day,user_id=actor.id,role_id=actor.role.id,reason='Stillborn offspring');self.db.add(death);self.db.flush();self.db.add(ExitModel(event_id=death.id,event_type_id=8,exit_type='death'))
                    self.db.add(AuditModel(user_id=actor.id,table='events',record_id=death.id,action='INSERT',new_values=dict(animal_id=a.id,event_type_id=8,exit_type='death',date=data.date.isoformat())))
        self.db.add(AuditModel(user_id=actor.id,table='events',record_id=event.id,action='INSERT',new_values=dict(event_type_id=event.event_type_id,role_id=actor.role.id,**data.model_dump(mode='json'))));self.db.flush()
        return self.response(event)
