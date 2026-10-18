"""Add labelled monthly case samples without modifying existing cases."""
import json
from datetime import date
from sqlalchemy import select
from src.core.database import get_session_factory
from src.core.mapping import to_user
from src.core.models import AnimalModel, HealthCaseModel, RoleModel, UserModel
from src.features.health.domain.dto import CaseInput, CaseStatusInput
from src.features.health.infrastructure.repository import SQLHealthRepository

PREFIX = 'SIMULACIÓN · Gráfica sanitaria'
CODE = 'DEMO-PESO-001'


def seed(db):
    owner = db.scalar(select(UserModel).join(RoleModel, RoleModel.id == UserModel.role_id)
        .where(UserModel.active == True, RoleModel.name == 'owner')
        .order_by(UserModel.created_at, UserModel.id).limit(1).with_for_update())
    if owner is None:
        raise RuntimeError('No active owner is available')
    actor = to_user(owner)
    if 'health:cases:write' not in actor.role.permissions:
        raise RuntimeError('Owner lacks case write permission')
    demo = db.scalar(select(AnimalModel).where(AnimalModel.siniiga == CODE).with_for_update())
    if demo is None or demo.name != 'DEMO · Gráfica de peso':
        raise RuntimeError('Expected demo animal is unavailable; no changes were saved')
    today = date.today()
    index = today.year * 12 + today.month - 1 - 5
    repo = SQLHealthRepository(db)
    added = 0
    ids = []
    for i, (starts, closes) in enumerate(zip([1, 2, 1, 3, 2, 3], [1, 1, 0, 2, 1, 2])):
        month = date((index+i)//12, (index+i)%12+1, 1)
        start = month.replace(day=min(today.day, 5))
        end = month.replace(day=min(today.day, 15))
        for number in range(1, starts+1):
            reason = f'{PREFIX} · {month:%Y-%m} · Caso {number}'
            row = db.scalar(select(HealthCaseModel).where(HealthCaseModel.reason == reason).with_for_update())
            status = 'closed' if number <= closes else 'open'
            closed_date = end if status == 'closed' else None
            if row:
                if row.animal_id != demo.id or row.start_date != start or row.status != status or row.closed_date != closed_date:
                    raise RuntimeError('Existing demo case differs; no changes were saved')
            else:
                saved = repo.create_case(CaseInput(animal_id=demo.id, start_date=start, reason=reason,
                    notes='SIMULACIÓN: caso ficticio para visualizar la gráfica. No corresponde a una enfermedad ni atención real.'), actor)
                row = db.get(HealthCaseModel, saved['id'])
                if closed_date:
                    repo.change_status(row.id, CaseStatusInput(expected_status='open', status='closed', closed_date=closed_date), actor)
                added += 1
            ids.append(row.id)
    return dict(added=added, ids=ids, date_from=date(index//12,index%12+1,1).isoformat(), date_to=today.isoformat())


def main():
    try:
        factory=get_session_factory()
        with factory.begin() as db:
            result=seed(db)
        with factory() as db:
            from src.features.dashboard.infrastructure.routes import health_trend
            records=list(db.scalars(select(HealthCaseModel).where(HealthCaseModel.id.in_(result['ids']))))
            assert len(records)==12 and sum(r.status=='closed' for r in records)==7
            summary=health_trend(date.fromisoformat(result['date_from']),date.fromisoformat(result['date_to']),db=db)
            result.pop('ids')
            result['demo_cases']=len(records)
            result['demo_closed']=7
            result['chart']={k:summary[k] for k in ('started_total','closed_total','items')}
        print(json.dumps(result,ensure_ascii=False))
    except Exception as exc:
        print('Demo operation failed:',type(exc).__name__)
        if isinstance(exc,RuntimeError):print(str(exc))
        raise SystemExit(1)


if __name__=='__main__':
    main()
