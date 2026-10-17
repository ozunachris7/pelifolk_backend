"""Recorded unit prices and calculated material cost, independent of paid expenses."""
from datetime import date
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.models import (AuditModel, ProductModel, ProductPriceModel, UnitModel,
                             EventTreatmentModel, TreatmentDoseModel)
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.health.domain.dto import ProductPriceInput

router = APIRouter(prefix='/health', tags=['Product prices and calculated treatment costs'])


def current_prices(db, ids):
    rows = db.scalars(select(ProductPriceModel).where(ProductPriceModel.product_id.in_(ids),
        ProductPriceModel.effective_from <= date.today()).order_by(ProductPriceModel.effective_from.desc())) if ids else []
    result = {}
    for row in rows:
        if row.product_id not in result:
            result[row.product_id] = dict(effective_from=row.effective_from,cost=str(row.cost))
    return result


def product(db, product_id, lock=False):
    query = select(ProductModel).where(ProductModel.id == product_id)
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise ApplicationError('Product not found',404)
    return row


def save_price(db, product_id, data, actor):
    row = product(db,product_id,True)
    if data.expected_unit_id is not None and data.expected_unit_id != row.unit_id:
        raise ApplicationError('Product unit changed before price entry',409)
    if db.scalar(select(ProductPriceModel.product_id).where(ProductPriceModel.product_id==product_id,
            ProductPriceModel.effective_from==data.effective_from).with_for_update()):
        raise ApplicationError('Product price already exists on date',409)
    db.add(ProductPriceModel(product_id=product_id,**data.model_dump(exclude={'expected_unit_id'})))
    response = dict(effective_from=data.effective_from.isoformat(),cost=str(data.cost))
    db.add(AuditModel(user_id=actor.id,table='product_prices',record_id=product_id,action='INSERT',
        new_values=dict(product_id=product_id,unit_id=row.unit_id,**response)))
    db.flush()
    return response


@router.get('/products/{product_id}/prices', dependencies=[Depends(require_permission('health:read'))])
def prices(product_id: UUID, offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),
           actor=Depends(require_permission('finance:read')),db: Session=Depends(get_db,scope='function')):
    pid=str(product_id);p=product(db,pid)
    query=select(ProductPriceModel).where(ProductPriceModel.product_id==pid)
    count=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(ProductPriceModel.effective_from.desc()).offset(offset).limit(limit))
    return dict(product=dict(id=p.id,name=p.name,unit_code=db.get(UnitModel,p.unit_id).code),as_of=date.today(),
        current_price=current_prices(db,[pid]).get(pid),items=[dict(effective_from=r.effective_from,cost=str(r.cost)) for r in rows],
        total=count,offset=offset,limit=limit)


@router.post('/products/{product_id}/prices',status_code=201,dependencies=[Depends(require_permission('health:read'))])
def create_price(product_id: UUID,data: ProductPriceInput,actor=Depends(require_permission('finance:write')),
                 db: Session=Depends(get_db,scope='function')):
    return save_price(db,str(product_id),data,actor)


@router.get('/treatments/{event_id}/products/{product_id}/cost',dependencies=[Depends(require_permission('health:read'))])
def treatment_cost(event_id: UUID,product_id: UUID,offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),
                   actor=Depends(require_permission('finance:read')),db: Session=Depends(get_db,scope='function')):
    eid,pid=str(event_id),str(product_id)
    if db.get(EventTreatmentModel,(eid,pid)) is None:
        raise ApplicationError('Treatment not found',404)
    p=product(db,pid)
    doses=db.scalars(select(TreatmentDoseModel).where(TreatmentDoseModel.treatment_event_id==eid,TreatmentDoseModel.product_id==pid)
        .order_by(TreatmentDoseModel.clinical_date,TreatmentDoseModel.applied_at_utc,TreatmentDoseModel.id)).all()
    from .costing import value_doses
    items=value_doses(db,doses)
    known=sum((Decimal(r['cost']) for r in items if r['cost'] is not None),Decimal('0.00'))
    count=sum(r['cost'] is not None for r in items)
    return dict(product_unit=db.get(UnitModel,p.unit_id).code,known_cost=str(known),priced_applications=count,
        unknown_applications=len(doses)-count,total=len(doses),offset=offset,limit=limit,items=items[offset:offset+limit],
        status='no_applications' if not doses else 'complete' if count==len(doses) else 'partial')
