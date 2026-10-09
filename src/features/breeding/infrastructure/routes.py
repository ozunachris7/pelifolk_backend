from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,Query
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.models import BirthTypeModel
from sqlalchemy import select
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.breeding.domain.dto import MatingInput,PregnancyInput,BirthInput,BreedingEvent,EventPage,BreedingHistory,AnimalSummary,BirthTypeResponse
from .repository import SQLBreedingRepository
router=APIRouter(prefix='/breeding',tags=['Breeding'])
def repository(db: Session=Depends(get_db,scope='function')):return SQLBreedingRepository(db)
@router.get('/animal-options',response_model=list[AnimalSummary])
def options(q: str=Query('',max_length=100),sex: Literal['male','female']|None=None,actor=Depends(require_permission('breeding:read')),repo=Depends(repository)):return repo.options(q.strip(),sex)
@router.get('/birth-types',response_model=list[BirthTypeResponse])
def birth_types(actor=Depends(require_permission('breeding:read')),repo=Depends(repository)):return [dict(id=b.id,name=b.name) for b in repo.db.scalars(select(BirthTypeModel).order_by(BirthTypeModel.name))]
@router.get('/events',response_model=EventPage)
def events(kind: Literal['mating','pregnancy','birth']|None=None,q: str=Query('',max_length=100),animal_id: UUID|None=None,offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),actor=Depends(require_permission('breeding:read')),repo=Depends(repository)):return repo.page(kind,q.strip(),offset,limit,str(animal_id) if animal_id else None)
@router.get('/animals/{animal_id}/history',response_model=BreedingHistory)
def history(animal_id: UUID,actor=Depends(require_permission('breeding:read')),repo=Depends(repository)):return repo.history(str(animal_id))
@router.post('/matings',response_model=BreedingEvent,status_code=201)
def mating(data: MatingInput,actor=Depends(require_permission('breeding:write')),repo=Depends(repository)):return repo.create('mating',data,actor)
@router.post('/pregnancy-diagnoses',response_model=BreedingEvent,status_code=201)
def pregnancy(data: PregnancyInput,actor=Depends(require_permission('breeding:write')),repo=Depends(repository)):return repo.create('pregnancy',data,actor)
@router.post('/births',response_model=BreedingEvent,status_code=201)
def birth(data: BirthInput,actor=Depends(require_permission('breeding:write')),repo=Depends(repository)):return repo.create('birth',data,actor)
