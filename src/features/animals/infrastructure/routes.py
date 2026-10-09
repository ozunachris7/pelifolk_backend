from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.animals.application.manage_animals import ManageAnimals
from src.features.animals.domain.dto import AnimalInput, AnimalPage, AnimalResponse, BreedInput, BreedResponse
from .repository import SQLAnimalRepository

router = APIRouter(tags=['Animals'])


def repository(db: Session = Depends(get_db, scope='function')):
    return SQLAnimalRepository(db)


@router.get('/breeds', response_model=list[BreedResponse])
def breeds(actor=Depends(require_permission('animals:read')), repo=Depends(repository)):
    return repo.breeds()


@router.post('/breeds', response_model=BreedResponse, status_code=201)
def create_breed(data: BreedInput, actor=Depends(require_permission('animals:write')), repo=Depends(repository)):
    return repo.create_breed(data.name, actor.id)


@router.put('/breeds/{breed_id}', response_model=BreedResponse)
def update_breed(data: BreedInput, breed_id: int = Path(gt=0),
                 actor=Depends(require_permission('animals:write')), repo=Depends(repository)):
    return repo.update_breed(breed_id, data.name, actor.id)


@router.delete('/breeds/{breed_id}', status_code=204)
def delete_breed(breed_id: int = Path(gt=0), actor=Depends(require_permission('animals:write')),
                 repo=Depends(repository)):
    repo.delete_breed(breed_id, actor.id)
    return Response(status_code=204)


@router.get('/animals', response_model=AnimalPage)
def animals(q: str = Query('', max_length=100), sex: Literal['male', 'female'] | None = None,
            offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), exclude_id: UUID | None = None, active: bool | None = None,
            actor=Depends(require_permission('animals:read')), repo=Depends(repository)):
    return repo.list(q.strip(), sex, offset, limit, str(exclude_id) if exclude_id else None, active)


@router.get('/animals/{animal_id}', response_model=AnimalResponse)
def animal(animal_id: UUID, actor=Depends(require_permission('animals:read')), repo=Depends(repository)):
    return repo.get(str(animal_id))


@router.post('/animals', response_model=AnimalResponse, status_code=201)
def create_animal(data: AnimalInput, actor=Depends(require_permission('animals:write')), repo=Depends(repository)):
    return ManageAnimals(repo).save(data, actor)


@router.put('/animals/{animal_id}', response_model=AnimalResponse)
def update_animal(animal_id: UUID, data: AnimalInput, actor=Depends(require_permission('animals:write')), repo=Depends(repository)):
    return ManageAnimals(repo).save(data, actor, str(animal_id))
