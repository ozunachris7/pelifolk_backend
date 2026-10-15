from decimal import Decimal
from sqlalchemy import func, or_, select
from src.core.errors import ApplicationError
from src.core.herd import effective_exit_query
from src.core.models import (AnimalModel, AuditModel, EventModel, ExitModel, ExpenseCategoryModel,
    IncomeCategoryModel, ExpenseModel, IncomeModel, SupplierModel, ExpenseAllocationModel)


class SQLFinanceRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def category_model(kind):
        return ExpenseCategoryModel if kind == 'expense' else IncomeCategoryModel

    @staticmethod
    def category_response(row):
        return dict(id=row.id, name=row.name)

    @staticmethod
    def supplier_response(row):
        return {key:getattr(row,key) for key in ('id','name','phone','email','address','active')}

    @staticmethod
    def sale_response(event, animal):
        return dict(id=event.id,animal_id=animal.id,animal_name=animal.name,siniiga=animal.siniiga,date=event.date.date())

    def audit(self, table, row_id, actor, before, after):
        self.db.add(AuditModel(user_id=actor.id,table=table,record_id=str(row_id),action='UPDATE' if before is not None else 'INSERT',old_values=before,new_values=after))

    def categories(self, kind):
        model = self.category_model(kind)
        return [self.category_response(r) for r in self.db.scalars(select(model).order_by(model.name,model.id))]

    def save_category(self, kind, data, actor, category_id=None):
        model = self.category_model(kind)
        row = self.db.scalar(select(model).where(model.id==category_id).with_for_update()) if category_id else model()
        if row is None:
            raise ApplicationError('Finance category not found',404)
        if self.db.scalar(select(model.id).where(func.lower(model.name)==data.name.lower(),model.id!=(category_id or 0)).limit(1)):
            raise ApplicationError('Finance category already exists',409)
        before = self.category_response(row) if category_id else None
        row.name = data.name
        self.db.add(row);self.db.flush()
        response = self.category_response(row)
        self.audit(model.__tablename__,row.id,actor,before,response)
        return response

    def delete_category(self, kind, category_id, actor):
        model = self.category_model(kind)
        row = self.db.scalar(select(model).where(model.id==category_id).with_for_update())
        if row is None:
            raise ApplicationError('Finance category not found',404)
        record = ExpenseModel if kind == 'expense' else IncomeModel
        column = record.expense_category_id if kind == 'expense' else record.income_category_id
        if self.db.scalar(select(record.id).where(column==category_id).limit(1).with_for_update()):
            raise ApplicationError('Finance category has records',409)
        before = self.category_response(row)
        self.db.delete(row);self.db.flush()
        self.db.add(AuditModel(user_id=actor.id,table=model.__tablename__,record_id=str(category_id),action='DELETE',old_values=before))

    def suppliers(self, q, active, offset, limit):
        query = select(SupplierModel)
        if q:
            query = query.where(or_(SupplierModel.name.icontains(q,autoescape=True),SupplierModel.phone.icontains(q,autoescape=True),SupplierModel.email.icontains(q,autoescape=True)))
        if active is not None:
            query = query.where(SupplierModel.active==active)
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.scalars(query.order_by(SupplierModel.name,SupplierModel.id).offset(offset).limit(limit))
        return dict(items=[self.supplier_response(r) for r in rows],total=total,offset=offset,limit=limit)

    def save_supplier(self, data, actor, supplier_id=None):
        row = self.db.scalar(select(SupplierModel).where(SupplierModel.id==supplier_id).with_for_update()) if supplier_id else SupplierModel()
        if row is None:
            raise ApplicationError('Supplier not found',404)
        if self.db.scalar(select(SupplierModel.id).where(func.lower(SupplierModel.name)==data.name.lower(),SupplierModel.id!=(supplier_id or '')).limit(1)):
            raise ApplicationError('Supplier already exists',409)
        before = self.supplier_response(row) if supplier_id else None
        for key,value in data.model_dump(mode='json').items():
            setattr(row,key,value)
        self.db.add(row);self.db.flush()
        response = self.supplier_response(row)
        self.audit('suppliers',row.id,actor,before,response)
        return response

    @staticmethod
    def range(query, column, date_from, date_to):
        if date_from:
            query = query.where(column>=date_from)
        if date_to:
            query = query.where(column<=date_to)
        return query

    def money_query(self, kind):
        if kind == 'expense':
            count = select(func.count(ExpenseAllocationModel.id)).where(ExpenseAllocationModel.expense_id==ExpenseModel.id).correlate(ExpenseModel).scalar_subquery()
            return select(ExpenseModel,ExpenseCategoryModel,SupplierModel,count).join(ExpenseCategoryModel,ExpenseCategoryModel.id==ExpenseModel.expense_category_id).outerjoin(SupplierModel,SupplierModel.id==ExpenseModel.supplier_id)
        return select(IncomeModel,IncomeCategoryModel,EventModel,AnimalModel).join(IncomeCategoryModel,IncomeCategoryModel.id==IncomeModel.income_category_id).outerjoin(EventModel,EventModel.id==IncomeModel.exit_event_id).outerjoin(AnimalModel,AnimalModel.id==EventModel.animal_id)

    def money_response(self, kind, row):
        record, category = row[:2]
        result = dict(id=record.id,category=self.category_response(category),amount=record.amount,date=record.date,description=record.description)
        if kind == 'expense':
            result['supplier'] = self.supplier_response(row[2]) if row[2] else None
            result['allocation_count'] = row[3] if len(row)>3 else 0
        else:
            result['sale'] = self.sale_response(row[2],row[3]) if row[2] else None
        return result

    def money_page(self, kind, q, category_id, date_from, date_to, offset, limit):
        model = ExpenseModel if kind == 'expense' else IncomeModel
        category = self.category_model(kind)
        column = model.expense_category_id if kind == 'expense' else model.income_category_id
        query = self.range(self.money_query(kind),model.date,date_from,date_to)
        if category_id:
            query = query.where(column==category_id)
        if q:
            conditions = [model.description.icontains(q,autoescape=True),category.name.icontains(q,autoescape=True)]
            conditions += [SupplierModel.name.icontains(q,autoescape=True)] if kind=='expense' else [AnimalModel.name.icontains(q,autoescape=True),AnimalModel.siniiga.icontains(q,autoescape=True)]
            query = query.where(or_(*conditions))
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.db.execute(query.order_by(model.date.desc(),model.id).offset(offset).limit(limit))
        return dict(items=[self.money_response(kind,r) for r in rows],total=total,offset=offset,limit=limit)

    def summary(self, date_from, date_to):
        values = []
        for model in (IncomeModel,ExpenseModel):
            query = self.range(select(func.coalesce(func.sum(model.amount),0),func.count(model.id)),model.date,date_from,date_to)
            total,count = self.db.execute(query).one()
            values.append((Decimal(total).quantize(Decimal('0.01')),count))
        income,expense = values
        return dict(income_total=income[0],expense_total=expense[0],balance=income[0]-expense[0],income_count=income[1],expense_count=expense[1])

    def sale_options(self, q, income_id=None):
        query = effective_exit_query().add_columns(AnimalModel).join(AnimalModel,AnimalModel.id==EventModel.animal_id).where(ExitModel.exit_type=='sale')
        used = select(IncomeModel.exit_event_id).where(IncomeModel.exit_event_id.is_not(None))
        if income_id:
            used = used.where(IncomeModel.id!=income_id)
        query = query.where(EventModel.id.not_in(used))
        if q:
            query = query.where(or_(AnimalModel.name.icontains(q,autoescape=True),AnimalModel.siniiga.icontains(q,autoescape=True)))
        return [self.sale_response(event,animal) for event,exit,animal in self.db.execute(query.order_by(EventModel.date.desc(),EventModel.id).limit(100))]

    def save_money(self, kind, data, actor, record_id=None):
        model = ExpenseModel if kind == 'expense' else IncomeModel
        # Match category deletion's lock order: category before financial record.
        category_model = self.category_model(kind)
        if not self.db.scalar(select(category_model).where(category_model.id==data.category_id).with_for_update()):
            raise ApplicationError('Finance category not found',422)
        row = self.db.scalar(select(model).where(model.id==record_id).with_for_update()) if record_id else model()
        if row is None:
            raise ApplicationError('Finance record not found',404)
        before = None
        if record_id:
            before = {key:(str(value) if key=='amount' else value.isoformat() if key=='date' else value) for key,value in ((c.name,getattr(row,c.name)) for c in model.__table__.columns)}
        if kind == 'expense':
            supplier_id = str(data.supplier_id) if data.supplier_id else None
            if supplier_id:
                supplier = self.db.scalar(select(SupplierModel).where(SupplierModel.id==supplier_id).with_for_update())
                if supplier is None:
                    raise ApplicationError('Supplier not found',422)
                if not supplier.active and supplier_id != row.supplier_id:
                    raise ApplicationError('Supplier is inactive',409)
            row.expense_category_id = data.category_id
            row.supplier_id = supplier_id
        else:
            exit_id = str(data.exit_event_id) if data.exit_event_id else None
            if exit_id:
                sale = self.db.execute(effective_exit_query().where(EventModel.id==exit_id).with_for_update()).first()
                if sale is None or sale[1].exit_type!='sale':
                    raise ApplicationError('Income requires a sale exit',422)
                if data.date < sale[0].date.date():
                    raise ApplicationError('Income date is before sale date',422)
                if self.db.scalar(select(IncomeModel.id).where(IncomeModel.exit_event_id==exit_id,IncomeModel.id!=(record_id or '')).limit(1).with_for_update()):
                    raise ApplicationError('Sale already has an income',409)
            row.income_category_id = data.category_id
            row.exit_event_id = exit_id
        row.amount = data.amount
        row.date = data.date
        row.description = data.description or None
        self.db.add(row);self.db.flush()
        after = {key:(str(value) if key=='amount' else value.isoformat() if key=='date' else value) for key,value in ((c.name,getattr(row,c.name)) for c in model.__table__.columns)}
        self.audit(model.__tablename__,row.id,actor,before,after)
        self.db.flush()
        return self.money_response(kind,self.db.execute(self.money_query(kind).where(model.id==row.id)).one())
