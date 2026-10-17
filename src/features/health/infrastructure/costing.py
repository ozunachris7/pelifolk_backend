from bisect import bisect_right
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select
from src.core.models import ProductModel, ProductPriceModel, UnitModel


def value_doses(db, doses):
    if not doses:
        return []
    ids={d.product_id for d in doses}
    products={p.id:p for p in db.scalars(select(ProductModel).where(ProductModel.id.in_(ids)))}
    history=defaultdict(list)
    for price in db.scalars(select(ProductPriceModel).where(ProductPriceModel.product_id.in_(ids)).order_by(ProductPriceModel.effective_from)):
        history[price.product_id].append(price)
    dates={key:[p.effective_from for p in rows] for key,rows in history.items()}
    units={u.id:u.code for u in db.scalars(select(UnitModel).where(UnitModel.id.in_({d.dose_unit_id for d in doses})))}
    result=[]
    for d in doses:
        p=products[d.product_id]
        index=bisect_right(dates.get(d.product_id,[]),d.clinical_date)-1
        price=history[d.product_id][index] if index>=0 else None
        reason='unit_mismatch' if d.dose_unit_id!=p.unit_id else 'missing_price' if price is None else None
        cost=None if reason else (d.dose_value*price.cost).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
        result.append(dict(dose_id=d.id,date=d.clinical_date,quantity=str(d.dose_value),unit_code=units[d.dose_unit_id],
            unit_cost=str(price.cost) if price and reason is None else None,effective_from=price.effective_from if price and reason is None else None,
            cost=str(cost) if cost is not None else None,unknown_reason=reason))
    return result
