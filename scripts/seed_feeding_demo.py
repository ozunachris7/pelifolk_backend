"""Insert clearly labelled feeding samples, without changing existing ranch data."""
import json
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import select
from src.core.database import get_session_factory
from src.core.mapping import to_user
from src.core.models import AnimalModel, FeedModel, FeedPriceModel, FeedingModel, RoleModel, UnitModel, UserModel
from src.features.animals.domain.dto import AnimalInput
from src.features.animals.infrastructure.repository import SQLAnimalRepository
from src.features.feeding.domain.dto import FeedCreateInput, FeedingInput, PriceInput
from src.features.feeding.infrastructure.repository import SQLFeedingRepository

CODE = 'DEMO-PESO-001'
NAME = 'DEMO · Gráfica de peso'
PREFIX = 'SIMULACIÓN · Gráfica alimentación'


def seed(db):
    owner = db.scalar(select(UserModel).join(RoleModel, RoleModel.id == UserModel.role_id)
        .where(UserModel.active == True, RoleModel.name == 'owner')
        .order_by(UserModel.created_at, UserModel.id).limit(1).with_for_update())
    if owner is None:
        raise RuntimeError('No active owner is available')
    actor = to_user(owner)
    if not {'animals:write', 'feeding:write'}.issubset(actor.role.permissions):
        raise RuntimeError('Owner lacks required animal or feeding permissions')
    today = date.today()
    index = today.year * 12 + today.month - 1 - 5
    months = [date((index + i) // 12, (index + i) % 12 + 1, min(today.day, 12)) for i in range(6)]
    demo = db.scalar(select(AnimalModel).where(AnimalModel.siniiga == CODE).with_for_update())
    if demo is None:
        saved = SQLAnimalRepository(db).save(AnimalInput(name=NAME, siniiga=CODE,
            sex='female', birth_date=months[0] - timedelta(days=90), origin='other',
            is_breeder=False, breeds=[]), actor.id)
        demo = db.get(AnimalModel, saved.id)
    if demo.name != NAME or demo.birth_date is None or demo.birth_date > months[0]:
        raise RuntimeError('Demo animal identifier or birth date differs; no changes were saved')
    repo = SQLFeedingRepository(db)
    added = 0
    feeds = []
    plans = [
        ('kg', 'Alimento en kg', ['12.50', '16.00', '13.25', '19.75', '22.00', '18.50'], ['0.6500', '0.8000']),
        ('bag', 'Alimento en sacos', ['0.25', '0.50', '0.25', '0.75', '0.50', '1.00'], ['18.5000', '22.5000']),
    ]
    for code, label, quantities, prices in plans:
        unit = db.scalar(select(UnitModel).where(UnitModel.code == code))
        if unit is None:
            unit = UnitModel(code=code)
            db.add(unit); db.flush()
        name = f'{PREFIX} · {label}'
        feed = db.scalar(select(FeedModel).where(FeedModel.name == name).with_for_update())
        if feed is None:
            response = repo.save_feed(FeedCreateInput(name=name, unit_id=unit.id), actor)
            feed = db.get(FeedModel, response['id'])
        if feed.unit_id != unit.id:
            raise RuntimeError('Demo feed has another unit; no changes were saved')
        for day, value in zip([months[0].replace(day=1), months[3].replace(day=1)], prices):
            price = db.get(FeedPriceModel, (feed.id, day))
            if price is None:
                repo.add_price(feed.id, PriceInput(effective_from=day, unit_cost=Decimal(value)), actor)
            elif price.unit_cost != Decimal(value):
                raise RuntimeError('Demo price differs; no changes were saved')
        for day, quantity in zip(months, quantities):
            existing = list(db.scalars(select(FeedingModel).where(FeedingModel.feed_id == feed.id,
                FeedingModel.date == day, FeedingModel.animal_id == demo.id).with_for_update()))
            if existing:
                if len(existing) != 1 or existing[0].quantity != Decimal(quantity):
                    raise RuntimeError('Demo consumption differs; no changes were saved')
            else:
                repo.create(FeedingInput(animal_id=demo.id, feed_id=feed.id,
                    date=day, quantity=Decimal(quantity)), actor)
                added += 1
        feeds.append(dict(id=feed.id, name=feed.name, unit=code))
    return dict(animal_id=demo.id, animal=demo.name, added=added,
        date_from=months[0].replace(day=1).isoformat(), date_to=today.isoformat(), feeds=feeds)


def main():
    try:
        factory = get_session_factory()
        with factory.begin() as db:
            result = seed(db)
        with factory() as db:
            from src.features.dashboard.infrastructure.routes import feeding_trend
            summary = feeding_trend(date.fromisoformat(result['date_from']), date.fromisoformat(result['date_to']), db=db)
            for feed in result['feeds']:
                count = len(list(db.scalars(select(FeedingModel.id).where(
                    FeedingModel.feed_id == feed['id'], FeedingModel.animal_id == result['animal_id']))))
                if count < 6:
                    raise RuntimeError('Persisted demo verification failed')
            result['chart'] = {k: summary[k] for k in ('consumption_count', 'unpriced_count', 'total_cost', 'quantities')}
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print('Demo operation failed:', type(exc).__name__)
        if isinstance(exc, RuntimeError):
            print(str(exc))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
