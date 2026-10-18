from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.weights.domain.dto import WeightInput, WeightResponse, WeightPage, WeightHistory, AnimalSummary
from .repository import SQLWeightRepository

router = APIRouter(prefix='/weights', tags=['Weights'])

def repository(db: Session = Depends(get_db, scope='function')):
    return SQLWeightRepository(db)

@router.get('', response_model=WeightPage)
def weights(q: str = Query('', max_length=100), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), actor=Depends(require_permission('weights:read')), repo=Depends(repository)):
    return repo.page(q.strip(), offset, limit)

@router.get('/animal-options', response_model=list[AnimalSummary])
def options(q: str = Query('', max_length=100), limit: int = Query(50, ge=1, le=100), include_exited: bool = False, actor=Depends(require_permission('weights:read')), repo=Depends(repository)):
    return repo.options(q.strip(), limit, include_exited=include_exited)

@router.get('/animals/{animal_id}/history', response_model=WeightHistory)
def history(animal_id: UUID, actor=Depends(require_permission('weights:read')), repo=Depends(repository)):
    return repo.history(str(animal_id))

@router.post('', response_model=WeightResponse, status_code=201)
def create(data: WeightInput, actor=Depends(require_permission('weights:write')), repo=Depends(repository)):
    return repo.create(data, actor)
