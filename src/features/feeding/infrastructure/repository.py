from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func, or_, select
from src.core.errors import ApplicationError
from src.core.herd import ensure_in_herd, has_exited
from src.core.models import (AnimalModel, AnimalGroupModel, AuditModel, FeedModel,
    FeedPriceModel, FeedingModel, GroupAnimalModel, UnitModel)


class SQLFeedingRepository:
    def __init__(self,db):
        self.db=db

    def audit(self,table,record_id,actor,before,after):
        self.db.add(AuditModel(user_id=actor.id,table=table,record_id=record_id,action='UPDATE' if before else 'INSERT',old_values=before,new_values=after))

    def feed(self,feed_id,lock=False):
        statement=select(FeedModel).where(FeedModel.id==feed_id)
        row=self.db.scalar(statement.with_for_update() if lock else statement)
        if row is None:
            raise ApplicationError('Feed not found',404)
        return row

    def feed_response(self,row):
        price=self.db.scalar(select(FeedPriceModel).where(FeedPriceModel.feed_id==row.id,FeedPriceModel.effective_from<=date.today()).order_by(FeedPriceModel.effective_from.desc()).limit(1))
        return dict(id=row.id,name=row.name,unit_id=row.unit_id,unit_code=self.db.get(UnitModel,row.unit_id).code,current_unit_cost=str(price.unit_cost) if price else None,current_price_from=price.effective_from.isoformat() if price else None)

    def units(self):
        return [dict(id=u.id,code=u.code) for u in self.db.scalars(select(UnitModel).order_by(UnitModel.code))]

    def feeds(self,q,offset,limit):
        query=select(FeedModel)
        if q:
            query=query.where(FeedModel.name.icontains(q,autoescape=True))
        total=self.db.scalar(select(func.count()).select_from(query.subquery()))
        return dict(items=[self.feed_response(f) for f in self.db.scalars(query.order_by(FeedModel.name,FeedModel.id).offset(offset).limit(limit))],total=total,offset=offset,limit=limit)

    def save_feed(self,data,actor,feed_id=None):
        row=self.feed(feed_id,True) if feed_id else FeedModel()
        if not self.db.get(UnitModel,data.unit_id):
            raise ApplicationError('Feed unit not found',422)
        if self.db.scalar(select(FeedModel.id).where(func.lower(FeedModel.name)==data.name.lower(),FeedModel.id!=(feed_id or '')).limit(1)):
            raise ApplicationError('Feed already exists',409)
        if feed_id and row.unit_id!=data.unit_id and (self.db.scalar(select(FeedPriceModel.feed_id).where(FeedPriceModel.feed_id==feed_id).limit(1).with_for_update()) or self.db.scalar(select(FeedingModel.id).where(FeedingModel.feed_id==feed_id).limit(1).with_for_update())):
            raise ApplicationError('Feed unit has history',409)
        before=self.feed_response(row) if feed_id else None
        row.name=data.name;row.unit_id=data.unit_id
        self.db.add(row);self.db.flush()
        response=self.feed_response(row);self.audit('feeds',row.id,actor,before,response)
        initial_price=getattr(data,'initial_price',None)
        if not feed_id and initial_price is not None:
            self.add_price(row.id,initial_price,actor)
        return self.feed_response(row)

    def prices(self,feed_id):
        self.feed(feed_id)
        return [dict(effective_from=p.effective_from,unit_cost=p.unit_cost) for p in self.db.scalars(select(FeedPriceModel).where(FeedPriceModel.feed_id==feed_id).order_by(FeedPriceModel.effective_from.desc()))]

    def add_price(self,feed_id,data,actor):
        self.feed(feed_id,True)
        if self.db.get(FeedPriceModel,(feed_id,data.effective_from)):
            raise ApplicationError('Feed price already exists on date',409)
        row=FeedPriceModel(feed_id=feed_id,effective_from=data.effective_from,unit_cost=data.unit_cost)
        self.db.add(row);self.db.flush()
        self.audit('feed_prices',feed_id,actor,None,dict(feed_id=feed_id,**data.model_dump(mode='json')))
        return dict(effective_from=row.effective_from,unit_cost=row.unit_cost)

    def options(self,kind,q):
        model=AnimalModel if kind=='animal' else AnimalGroupModel
        query=select(model)
        if kind=='animal':
            query=query.where(~has_exited(AnimalModel.id,date.today()))
            if q:
                query=query.where(or_(model.name.icontains(q,autoescape=True),model.siniiga.icontains(q,autoescape=True)))
        else:
            query=query.where(model.active==True)
            if q:
                query=query.where(model.name.icontains(q,autoescape=True))
        return [dict(id=r.id,name=r.name,siniiga=r.siniiga if kind=='animal' else None) for r in self.db.scalars(query.order_by(model.name,model.id).limit(100))]

    @staticmethod
    def price_expression():
        return select(FeedPriceModel.unit_cost).where(FeedPriceModel.feed_id==FeedingModel.feed_id,FeedPriceModel.effective_from<=FeedingModel.date).order_by(FeedPriceModel.effective_from.desc()).limit(1).correlate(FeedingModel).scalar_subquery()
    def query(self):
        price=self.price_expression()
        start=select(FeedPriceModel.effective_from).where(FeedPriceModel.feed_id==FeedingModel.feed_id,FeedPriceModel.effective_from<=FeedingModel.date).order_by(FeedPriceModel.effective_from.desc()).limit(1).correlate(FeedingModel).scalar_subquery()
        return select(FeedingModel,FeedModel,AnimalModel,AnimalGroupModel,price,start).join(FeedModel,FeedModel.id==FeedingModel.feed_id).outerjoin(AnimalModel,AnimalModel.id==FeedingModel.animal_id).outerjoin(AnimalGroupModel,AnimalGroupModel.id==FeedingModel.group_id)

    def response(self,row):
        record,feed,animal,group,price,start=row
        cost=(record.quantity*price).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP) if price is not None else None
        return dict(id=record.id,feed=self.feed_response(feed),animal=dict(id=animal.id,name=animal.name,siniiga=animal.siniiga) if animal else None,group=dict(id=group.id,name=group.name,siniiga=None) if group else None,date=record.date,quantity=record.quantity,unit_cost=price,price_from=start,cost=cost)

    def page(self,q,animal_id,group_id,date_from,date_to,offset,limit):
        query=self.query()
        if q:
            query=query.where(or_(FeedModel.name.icontains(q,autoescape=True),AnimalModel.name.icontains(q,autoescape=True),AnimalModel.siniiga.icontains(q,autoescape=True),AnimalGroupModel.name.icontains(q,autoescape=True)))
        if animal_id:
            query=query.where(FeedingModel.animal_id==animal_id)
        if group_id:
            query=query.where(FeedingModel.group_id==group_id)
        if date_from:
            query=query.where(FeedingModel.date>=date_from)
        if date_to:
            query=query.where(FeedingModel.date<=date_to)
        # Round each consumption in MXN before summing so totals match displayed rows.
        total=unpriced=0
        total_cost=Decimal('0.00')
        for quantity,price in self.db.execute(query.with_only_columns(FeedingModel.quantity,self.price_expression(),maintain_column_froms=True)):
            total+=1
            if price is None:
                unpriced+=1
            else:
                total_cost+=(quantity*price).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
        rows=self.db.execute(query.order_by(FeedingModel.date.desc(),FeedingModel.id).offset(offset).limit(limit))
        return dict(items=[self.response(r) for r in rows],total=total,offset=offset,limit=limit,total_cost=total_cost,unpriced_count=unpriced)

    def create(self,data,actor):
        if data.animal_id:
            animal=self.db.scalar(select(AnimalModel).where(AnimalModel.id==str(data.animal_id)).with_for_update())
            if animal is None:
                raise ApplicationError('Animal not found',404)
            if animal.birth_date and data.date<animal.birth_date:
                raise ApplicationError('Feeding date is before birth',422)
            ensure_in_herd(self.db,animal.id,data.date)
        else:
            group=self.db.scalar(select(AnimalGroupModel).where(AnimalGroupModel.id==str(data.group_id)).with_for_update())
            if group is None:
                raise ApplicationError('Group not found',404)
            if not group.active:
                raise ApplicationError('Group is inactive',409)
            if not self.db.scalar(select(GroupAnimalModel.animal_id).where(GroupAnimalModel.group_id==group.id,GroupAnimalModel.start_date<=data.date,or_(GroupAnimalModel.end_date.is_(None),GroupAnimalModel.end_date>=data.date)).limit(1).with_for_update()):
                raise ApplicationError('Group has no members on feeding date',422)
        feed=self.feed(str(data.feed_id),True)
        price=self.db.scalar(select(FeedPriceModel).where(FeedPriceModel.feed_id==feed.id,FeedPriceModel.effective_from<=data.date).order_by(FeedPriceModel.effective_from.desc()).limit(1).with_for_update())
        if price is None:
            raise ApplicationError('Feed has no price on feeding date',422)
        row=FeedingModel(animal_id=str(data.animal_id) if data.animal_id else None,group_id=str(data.group_id) if data.group_id else None,feed_id=feed.id,date=data.date,quantity=data.quantity)
        self.db.add(row);self.db.flush()
        self.audit('feedings',row.id,actor,None,data.model_dump(mode='json'))
        return self.response(self.db.execute(self.query().where(FeedingModel.id==row.id)).one())
