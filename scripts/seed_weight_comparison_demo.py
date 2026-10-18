"""Add two clearly labelled animals with six fictitious measurements each."""
import json
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import select
from src.core.database import get_session_factory
from src.core.mapping import to_user
from src.core.models import AnimalModel, RoleModel, UserModel
from src.features.animals.domain.dto import AnimalInput
from src.features.animals.infrastructure.repository import SQLAnimalRepository
from src.features.weights.domain.dto import WeightInput
from src.features.weights.infrastructure.repository import SQLWeightRepository

MARKER='SIMULACIÓN DEMO_COMPARACION_PESOS_V1'


def seed(db):
    owner=db.scalar(select(UserModel).join(RoleModel,RoleModel.id==UserModel.role_id)
        .where(UserModel.active==True,RoleModel.name=='owner')
        .order_by(UserModel.created_at,UserModel.id).limit(1).with_for_update())
    if owner is None:raise RuntimeError('No active owner is available')
    actor=to_user(owner)
    if not {'animals:write','weights:write'}.issubset(actor.role.permissions):
        raise RuntimeError('Owner lacks animal or weight write permissions')
    today=date.today();repo=SQLWeightRepository(db);result=[];added=0
    plans=[('DEMO-COMP-002','DEMO · Comparación Brisa','female',[148,117,88,59,29,1],['17.80','20.50','23.20','25.10','28.80','31.40']),
           ('DEMO-COMP-003','DEMO · Comparación Canelo','male',[150,120,90,60,30,0],['19.20','22.80','25.40','24.60','30.20','34.60'])]
    for code,name,sex,offsets,values in plans:
        row=db.scalar(select(AnimalModel).where(AnimalModel.siniiga==code).with_for_update())
        if row is None:
            saved=SQLAnimalRepository(db).save(AnimalInput(name=name,siniiga=code,sex=sex,
                birth_date=today-timedelta(days=270),origin='other',is_breeder=False,breeds=[]),actor.id)
            row=db.get(AnimalModel,saved.id)
        if row.name!=name or row.sex!=sex:
            raise RuntimeError('Demo identifier belongs to a different animal; no changes were saved')
        plan=[(today-timedelta(days=offset),Decimal(value)) for offset,value in zip(offsets,values)]
        existing=repo.history(row.id)['items']
        if existing:
            if len(existing)!=6 or any(w['date']!=day or w['weight_kg']!=value or MARKER not in (w['notes'] or '') for w,(day,value) in zip(existing,plan)):
                raise RuntimeError('Existing demo weights differ; no changes were saved')
        else:
            for day,value in plan:
                repo.create(WeightInput(animal_id=row.id,date=day,weight_kg=value,
                    notes=f'{MARKER} · Peso ficticio para visualizar la comparación; no corresponde a una medición real.'),actor)
                added+=1
        result.append(dict(id=row.id,name=row.name,siniiga=row.siniiga))
    return dict(added_weights=added,animals=result)


def main():
    try:
        factory=get_session_factory()
        with factory.begin() as db:result=seed(db)
        with factory() as db:
            repo=SQLWeightRepository(db)
            for animal in result['animals']:
                history=repo.history(animal['id'])
                assert len(history['items'])==6 and all(MARKER in (w['notes'] or '') for w in history['items'])
                animal['weights']=[dict(date=str(w['date']),weight_kg=str(w['weight_kg'])) for w in history['items']]
        print(json.dumps(result,ensure_ascii=False))
    except Exception as exc:
        print('Demo operation failed:',type(exc).__name__)
        if isinstance(exc,RuntimeError):print(str(exc))
        raise SystemExit(1)


if __name__=='__main__':main()
