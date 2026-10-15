from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.features.auth.infrastructure.dependencies import require_permission
from .dto import WeaningInput,WeaningResponse,WeaningPage,WeaningOption
from .repository import SQLWeaningRepository

router=APIRouter(prefix='/weanings',tags=['Weaning'])


def repository(db:Session=Depends(get_db,scope='function')):
    return SQLWeaningRepository(db)


@router.get('/animal-options',response_model=list[WeaningOption])
def options(q:str=Query('',max_length=100),limit:int=Query(50,ge=1,le=100),
            actor=Depends(require_permission('weights:read')),repo=Depends(repository)):
    return repo.options(q.strip(),limit)


@router.get('',response_model=WeaningPage)
def listing(q:str=Query('',max_length=100),offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),
            actor=Depends(require_permission('weights:read')),repo=Depends(repository)):
    return repo.page(q.strip(),offset,limit)


@router.get('/animals/{animal_id}',response_model=WeaningResponse|None)
def history(animal_id:UUID,actor=Depends(require_permission('weights:read')),repo=Depends(repository)):
    from src.core.models import EventWeaningModel
    repo.animal(str(animal_id))
    row=repo.db.execute(repo.query().where(EventWeaningModel.animal_id==str(animal_id))).first()
    return repo.response(row) if row else None


@router.post('',response_model=WeaningResponse,status_code=201)
def create(data:WeaningInput,actor=Depends(require_permission('weights:write')),repo=Depends(repository)):
    return repo.create(data,actor)
