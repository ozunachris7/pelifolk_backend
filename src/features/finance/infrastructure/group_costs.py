"""Read-only equal allocation by recorded group membership on each source date."""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.herd import effective_exit_query
from src.core.models import (AnimalModel, AnimalGroupModel, GroupAnimalModel, ExpenseModel,
                             ExpenseAllocationModel, FeedingModel, FeedModel, EventModel)
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.feeding.infrastructure.repository import SQLFeedingRepository
from .allocations import money, target
from .routes import date_range

router = APIRouter(prefix='/finance/group-costs',tags=['Calculated group cost distribution'])


def split_cents(amount, ids):
    """Stable ID order resolves remainder cents; shares always sum to the source amount."""
    ids=sorted(set(ids))
    if not ids:
        return {}
    base,remainder=divmod(int(amount*100),len(ids))
    return {key:Decimal(base+(n<remainder))/100 for n,key in enumerate(ids)}


def sources(db, group_ids, date_from, date_to, feeding):
    end=min(date_to or date.today(),date.today())
    allocated=select(ExpenseAllocationModel.expense_id).where(ExpenseAllocationModel.group_id.in_(group_ids))
    query=select(ExpenseModel).where(ExpenseModel.id.in_(allocated),ExpenseModel.date<=end)
    if date_from:
        query=query.where(ExpenseModel.date>=date_from)
    expenses=db.scalars(query).all()
    by_expense=defaultdict(list)
    if expenses:
        for r in db.scalars(select(ExpenseAllocationModel).where(ExpenseAllocationModel.expense_id.in_([e.id for e in expenses]))):
            by_expense[r.expense_id].append(r)
    result=[]
    for expense in expenses:
        rows=by_expense[expense.id]
        for row,amount in zip(rows,money(expense.amount,rows)):
            if row.group_id in group_ids:
                result.append(dict(id=row.id,kind='expense',group_id=row.group_id,date=expense.date,
                    title=expense.description or 'Gasto asignado al lote',amount=amount,
                    expense_id=expense.id,original_amount=expense.amount,percentage=row.percentage))
    if feeding:
        query=select(FeedingModel,FeedModel.name,SQLFeedingRepository.price_expression()).join(FeedModel,FeedModel.id==FeedingModel.feed_id).where(
            FeedingModel.group_id.in_(group_ids),FeedingModel.date<=end)
        if date_from:
            query=query.where(FeedingModel.date>=date_from)
        for row,name,price in db.execute(query):
            result.append(dict(id=row.id,kind='feeding',group_id=row.group_id,date=row.date,title=name,
                amount=(row.quantity*price).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP) if price is not None else None))
    return result


def distribute(db, raw):
    if not raw:
        return [],{}
    groups={r['group_id'] for r in raw};first=min(r['date'] for r in raw);last=max(r['date'] for r in raw)
    periods=defaultdict(list);animals={}
    query=select(GroupAnimalModel,AnimalModel).join(AnimalModel,AnimalModel.id==GroupAnimalModel.animal_id).where(
        GroupAnimalModel.group_id.in_(groups),GroupAnimalModel.start_date<=last,
        or_(GroupAnimalModel.end_date.is_(None),GroupAnimalModel.end_date>=first))
    for period,animal in db.execute(query):
        periods[period.group_id].append(period);animals[animal.id]=animal
    exits={}
    if animals:
        for event,_ in db.execute(effective_exit_query().where(EventModel.animal_id.in_(list(animals)))):
            exits[event.animal_id]=min(exits.get(event.animal_id,event.date.date()),event.date.date())
    names={g.id:g.name for g in db.scalars(select(AnimalGroupModel).where(AnimalGroupModel.id.in_(groups)))}
    cache={}
    for r in raw:
        key=(r['group_id'],r['date']);day=r['date']
        if key not in cache:
            cache[key]=sorted({p.animal_id for p in periods[r['group_id']]
                if p.start_date<=day and (p.end_date is None or p.end_date>=day)
                and (animals[p.animal_id].birth_date is None or animals[p.animal_id].birth_date<=day)
                and (p.animal_id not in exits or exits[p.animal_id]>=day)})
        r['members']=cache[key];r['group_name']=names[r['group_id']]
        r['shares']=split_cents(r['amount'],r['members']) if r['amount'] is not None else {}
    return sorted(raw,key=lambda r:(r['date'],r['kind'],r['id']),reverse=True),animals


def summarize(raw, animals, kind, target_id, feeding):
    rows={};totals={key:Decimal('0.00') for key in ('source_expenses','allocated_expenses','unallocated_expenses','source_feeding','allocated_feeding','unallocated_feeding')}
    no_members=unpriced=0
    for r in raw:
        ids=r['members'];amount=r['amount'];bucket='expenses' if r['kind']=='expense' else 'feeding'
        if not ids:
            no_members+=1
        if amount is None:
            unpriced+=1
        else:
            totals['source_'+bucket]+=amount
            totals[('allocated_' if ids else 'unallocated_')+bucket]+=amount
        for key in ids:
            if kind=='animal' and key!=target_id:
                continue
            if key not in rows:
                a=animals[key]
                rows[key]=dict(animal=dict(id=a.id,name=a.name,siniiga=a.siniiga),expenses=Decimal('0.00'),feeding=Decimal('0.00'),expense_records=0,feeding_records=0,unpriced_feeding=0)
            row=rows[key]
            row['expense_records' if r['kind']=='expense' else 'feeding_records']+=1
            if amount is None:
                row['unpriced_feeding']+=1
            else:
                row[bucket]+=r['shares'][key]
    result=[]
    for row in rows.values():
        row['expenses']=f"{row['expenses']:.2f}"
        if feeding:
            row['feeding']=f"{row['feeding']:.2f}"
        else:
            for key in ('feeding','feeding_records','unpriced_feeding'):
                row.pop(key)
        result.append(row)
    result.sort(key=lambda r:((r['animal']['name'] or '').casefold(),r['animal']['id']))
    summary={k:f'{v:.2f}' for k,v in totals.items() if feeding or not k.endswith('feeding')}
    summary.update(source_count=len(raw),records_without_members=no_members,attributed_expenses=f"{sum((Decimal(r['expenses']) for r in result),Decimal('0.00')):.2f}")
    if feeding:
        summary['attributed_feeding']=f"{sum((Decimal(r['feeding']) for r in result),Decimal('0.00')):.2f}"
    if feeding:
        summary['unpriced_feeding']=unpriced
    return result,summary


def source_response(row, target_id=None):
    result={k:v for k,v in row.items() if k not in ('members','shares')}
    for key in ('amount','original_amount','percentage'):
        if key in result:
            result[key]=str(result[key]) if result[key] is not None else None
    result['member_count']=len(row['members'])
    result['status']='missing_price' if row['amount'] is None else 'no_members' if not row['members'] else 'distributed'
    if target_id:
        result['animal_amount']=f"{row['shares'][target_id]:.2f}" if target_id in row['shares'] else None
    return result


@router.get('')
def listing(kind: Literal['animal','group'],target_id: UUID,view: Literal['animals','sources']='animals',dates=Depends(date_range),
            offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),actor=Depends(require_permission('finance:read')),
            db: Session=Depends(get_db,scope='function')):
    tid=str(target_id);info=target(db,kind,tid);feeding='feeding:read' in actor.role.permissions
    groups={tid} if kind=='group' else set(db.scalars(select(GroupAnimalModel.group_id).where(GroupAnimalModel.animal_id==tid)))
    raw,animals=distribute(db,sources(db,groups,*dates,feeding))
    if kind=='animal':
        raw=[r for r in raw if tid in r['members']]
    rows,summary=summarize(raw,animals,kind,tid,feeding)
    if view=='sources':
        items=[source_response(r,tid if kind=='animal' else None) for r in raw[offset:offset+limit]];total=len(raw)
    else:
        items=rows[offset:offset+limit];total=len(rows)
    return dict(as_of=date.today(),kind=kind,target=info,view=view,date_from=dates[0],date_to=dates[1],
        basis='equal_members_on_source_date',summary=summary,items=items,total=total,offset=offset,limit=limit,
        feeding_included=feeding)


@router.get('/sources/{source_kind}/{source_id}')
def detail(source_kind: Literal['expense','feeding'],source_id: UUID,offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),
           actor=Depends(require_permission('finance:read')),db: Session=Depends(get_db,scope='function')):
    sid=str(source_id)
    if source_kind=='feeding':
        if 'feeding:read' not in actor.role.permissions:
            raise ApplicationError('Missing feeding permission',403)
        ref=db.get(FeedingModel,sid)
    else:
        ref=db.get(ExpenseAllocationModel,sid)
    if ref is None or ref.group_id is None:
        raise ApplicationError('Group cost source not found',404)
    if source_kind=='expense':
        day=db.get(ExpenseModel,ref.expense_id).date
    else:
        day=ref.date
    raw=sources(db,{ref.group_id},day,day,source_kind=='feeding')
    raw=[r for r in raw if r['id']==sid and r['kind']==source_kind]
    if not raw:
        raise ApplicationError('Group cost source not found',404)
    raw,animals=distribute(db,raw);r=raw[0]
    items=[dict(animal=dict(id=key,name=animals[key].name,siniiga=animals[key].siniiga),amount=f"{r['shares'][key]:.2f}" if key in r['shares'] else None)
        for key in r['members'][offset:offset+limit]]
    return dict(source=source_response(r),items=items,total=len(r['members']),offset=offset,limit=limit)
