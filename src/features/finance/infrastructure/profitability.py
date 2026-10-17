"""Financial result attributed from recorded ledger entries, with usage values kept separate."""
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import effective_exit_query
from src.core.models import (AnimalModel, ExpenseModel, ExpenseAllocationModel, HealthCaseModel,
    IncomeModel, EventModel, FeedingModel, FeedModel, TreatmentDoseModel, ProductModel)
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.feeding.infrastructure.repository import SQLFeedingRepository
from src.features.health.infrastructure.costing import value_doses
from .allocations import money
from .group_costs import distribute
from .repository import SQLFinanceRepository
from src.features.finance.domain.dto import MoneyResponse
from .routes import date_range

router=APIRouter(prefix='/finance/profitability',tags=['Attributed animal financial results'])
ZERO=Decimal('0.00')


def ranged(query,column,start,end):
    query=query.where(column<=end)
    return query.where(column>=start) if start else query


def collect(db, dates, permissions, operational=True):
    start,requested_end=dates;end=min(requested_end or date.today(),date.today())
    animals={a.id:a for a in db.scalars(select(AnimalModel))}
    rows={key:dict(animal=dict(id=a.id,name=a.name,siniiga=a.siniiga),status='not_born' if a.birth_date and a.birth_date>end else 'active',income=ZERO,
        direct_expenses=ZERO,case_expenses=ZERO,group_expenses=ZERO,income_count=0,expense_count=0) for key,a in animals.items()}
    entries=defaultdict(lambda:defaultdict(list))
    can_feed=operational and 'feeding:read' in permissions;can_health=operational and 'health:read' in permissions
    for r in rows.values():
        if can_feed:r['feeding']=dict(direct=ZERO,group=ZERO,known_cost=ZERO,records=0,unpriced=0)
        if can_health:r['medicines']=dict(known_cost=ZERO,applications=0,unpriced=0)
    for event,departure in db.execute(effective_exit_query().where(EventModel.date<=datetime.combine(end,time.max))):
        if event.animal_id in rows:rows[event.animal_id]['status']=departure.exit_type
    cases=dict(db.execute(select(HealthCaseModel.id,HealthCaseModel.animal_id)).all())
    expenses=db.scalars(ranged(select(ExpenseModel),ExpenseModel.date,start,end)).all()
    expense_map={e.id:e for e in expenses};shares=defaultdict(list)
    if expenses:
        for share in db.scalars(select(ExpenseAllocationModel).where(ExpenseAllocationModel.expense_id.in_(list(expense_map)))):
            shares[share.expense_id].append(share)
    assigned=defaultdict(lambda:ZERO);group_sources=[]

    def expense_entry(animal_id,expense,amount,via,source_id,group_name=None):
        if animal_id not in rows:return
        rows[animal_id][via+'_expenses']+=amount;rows[animal_id]['expense_count']+=1
        assigned[expense.id]+=amount
        entries[animal_id]['expenses'].append(dict(id=source_id,date=expense.date,title=expense.description or 'Gasto registrado',
            amount=f'{amount:.2f}',via=via,expense_id=expense.id,original_amount=str(expense.amount),group_name=group_name))

    for expense in expenses:
        allocations=shares[expense.id]
        for share,amount in zip(allocations,money(expense.amount,allocations)):
            if share.group_id:
                group_sources.append(dict(id=share.id,kind='expense',group_id=share.group_id,date=expense.date,
                    title=expense.description or 'Gasto del lote',amount=amount,expense_id=expense.id))
            else:
                key=share.animal_id or cases.get(share.health_case_id)
                expense_entry(key,expense,amount,'direct' if share.animal_id else 'case',share.id)
    if can_feed:
        query=ranged(select(FeedingModel,FeedModel.name,SQLFeedingRepository.price_expression()).join(FeedModel,FeedModel.id==FeedingModel.feed_id),FeedingModel.date,start,end)
        for record,name,price in db.execute(query):
            amount=(record.quantity*price).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP) if price is not None else None
            if record.group_id:
                group_sources.append(dict(id=record.id,kind='feeding',group_id=record.group_id,date=record.date,title=name,amount=amount))
            elif record.animal_id in rows:
                r=rows[record.animal_id]['feeding'];r['records']+=1
                if amount is None:r['unpriced']+=1
                else:r['direct']+=amount;r['known_cost']+=amount
                entries[record.animal_id]['feeding'].append(dict(id=record.id,date=record.date,title=name,amount=str(amount) if amount is not None else None,via='direct',unknown_reason='missing_price' if amount is None else None))
    group_sources,_=distribute(db,group_sources)
    for source in group_sources:
        for key in source['members']:
            if source['kind']=='expense':
                expense_entry(key,expense_map[source['expense_id']],source['shares'][key],'group',source['id'],source['group_name'])
            elif key in rows:
                r=rows[key]['feeding'];r['records']+=1
                amount=source['shares'].get(key)
                if amount is None:r['unpriced']+=1
                else:r['group']+=amount;r['known_cost']+=amount
                entries[key]['feeding'].append(dict(id=source['id'],date=source['date'],title=source['title'],amount=str(amount) if amount is not None else None,via='group',group_name=source['group_name'],unknown_reason='missing_price' if amount is None else None))
    incomes=db.execute(ranged(select(IncomeModel,EventModel).outerjoin(EventModel,EventModel.id==IncomeModel.exit_event_id),IncomeModel.date,start,end)).all()
    pending_incomes=[]
    for income,event in incomes:
        key=event.animal_id if event else income.animal_id
        if key in rows:
            rows[key]['income']+=income.amount;rows[key]['income_count']+=1
            entries[key]['incomes'].append(dict(id=income.id,date=income.date,title=income.description or 'Ingreso registrado',amount=str(income.amount),via='sale' if event else 'direct'))
        else:
            pending_incomes.append(dict(id=income.id,date=income.date,amount=str(income.amount),description=income.description))
    if can_health:
        dose_rows=db.execute(ranged(select(TreatmentDoseModel,EventModel.animal_id).join(EventModel,EventModel.id==TreatmentDoseModel.treatment_event_id),TreatmentDoseModel.clinical_date,start,end)).all()
        valued=value_doses(db,[d for d,_ in dose_rows])
        product_names=dict(db.execute(select(ProductModel.id,ProductModel.name).where(ProductModel.id.in_({d.product_id for d,_ in dose_rows}))).all()) if dose_rows else {}
        for (dose,key),value in zip(dose_rows,valued):
            if key not in rows:continue
            r=rows[key]['medicines'];r['applications']+=1
            if value['cost'] is None:r['unpriced']+=1
            else:r['known_cost']+=Decimal(value['cost'])
            entries[key]['medicines'].append(dict(id=dose.id,date=value['date'],title=f"{product_names[dose.product_id]} · {value['quantity']} {value['unit_code']}",amount=value['cost'],unknown_reason=value['unknown_reason'],via='application'))
    pending_expenses=[]
    for expense in expenses:
        residual=expense.amount-assigned[expense.id]
        if residual>0:
            pending_expenses.append(dict(id=expense.id,date=expense.date,amount=str(expense.amount),pending_amount=f'{residual:.2f}',description=expense.description))
    for r in rows.values():
        r['expenses']=r['direct_expenses']+r['case_expenses']+r['group_expenses']
        r['result']=r['income']-r['expenses']
    coverage=dict(expense_total=f'{sum((e.amount for e in expenses),ZERO):.2f}',
        attributed_expenses=f'{sum((r["expenses"] for r in rows.values()),ZERO):.2f}',
        pending_expenses=f'{sum((Decimal(e["pending_amount"]) for e in pending_expenses),ZERO):.2f}',
        pending_expense_count=len(pending_expenses),pending_income_count=len(pending_incomes),
        pending_income=f'{sum((Decimal(i["amount"]) for i in pending_incomes),ZERO):.2f}',
        status='pending_attribution' if pending_expenses or pending_incomes else 'attributed_records')
    return rows,entries,coverage,{'expenses':pending_expenses,'incomes':pending_incomes}


def encoded_row(row):
    result={key:f'{value:.2f}' if isinstance(value,Decimal) else value for key,value in row.items()}
    for section in ('feeding','medicines'):
        if section in result:result[section]={k:f'{v:.2f}' if isinstance(v,Decimal) else v for k,v in result[section].items()}
    return result


@router.get('')
def listing(q:str=Query('',max_length=100),animal_id:UUID|None=None,status:Literal['all','active','exited']='all',dates=Depends(date_range),
            offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),actor=Depends(require_permission('finance:read')),
            db:Session=Depends(get_db,scope='function')):
    rows,_,coverage,_=collect(db,dates,actor.role.permissions)
    needle=q.strip().casefold()
    selected=[r for r in rows.values() if (animal_id is None or r['animal']['id']==str(animal_id)) and (not needle or needle in (r['animal']['name'] or '').casefold() or needle in (r['animal']['siniiga'] or '').casefold())
        and (status=='all' or status=='active' and r['status']=='active' or status=='exited' and r['status'] not in ('active','not_born'))]
    selected.sort(key=lambda r:((r['animal']['name'] or '').casefold(),r['animal']['id']))
    summary={key:f'{sum((r[key] for r in selected),ZERO):.2f}' for key in ('income','expenses','result')}
    return dict(as_of=date.today(),date_from=dates[0],date_to=dates[1],basis='attributed_recorded_ledger',
        items=[encoded_row(r) for r in selected[offset:offset+limit]],total=len(selected),offset=offset,limit=limit,
        summary=summary,coverage=coverage,activity=dict(income_count=sum(r['income_count'] for r in selected),expense_count=sum(r['expense_count'] for r in selected)))


@router.get('/pending')
def pending(kind:Literal['expenses','incomes'],dates=Depends(date_range),offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),
            actor=Depends(require_permission('finance:read')),db:Session=Depends(get_db,scope='function')):
    _,_,_,pending=collect(db,dates,actor.role.permissions,False)
    records=sorted(pending[kind],key=lambda r:(r['date'],r['id']),reverse=True)
    repo=SQLFinanceRepository(db);model=ExpenseModel if kind=='expenses' else IncomeModel
    ids=[r['id'] for r in records[offset:offset+limit]]
    details={r[0].id:MoneyResponse.model_validate(repo.money_response('expense' if kind=='expenses' else 'income',r)).model_dump(mode='json') for r in db.execute(repo.money_query('expense' if kind=='expenses' else 'income').where(model.id.in_(ids)))} if ids else {}
    return dict(items=[dict(**r,record=details[r['id']]) for r in records[offset:offset+limit]],total=len(records),offset=offset,limit=limit)


@router.get('/{animal_id}/entries')
def entries(animal_id:UUID,section:Literal['incomes','expenses','feeding','medicines'],dates=Depends(date_range),
            offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),actor=Depends(require_permission('finance:read')),
            db:Session=Depends(get_db,scope='function')):
    if section=='feeding' and 'feeding:read' not in actor.role.permissions:raise ApplicationError('Missing feeding permission',403)
    if section=='medicines' and 'health:read' not in actor.role.permissions:raise ApplicationError('Missing health permission',403)
    key=str(animal_id);rows,records,_,_=collect(db,dates,actor.role.permissions)
    if key not in rows:raise ApplicationError('Animal not found',404)
    page=sorted(records[key][section],key=lambda r:(r['date'],r['id']),reverse=True)
    return dict(animal=rows[key]['animal'],section=section,items=page[offset:offset+limit],total=len(page),offset=offset,limit=limit)
