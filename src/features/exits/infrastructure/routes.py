from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.exits.domain.dto import AnimalSummary, ExitHistory, ExitInput, ExitPage, ExitResponse, ExitType
from .repository import SQLExitRepository

router = APIRouter(prefix='/exits', tags=['Exits'])


def repository(db: Session = Depends(get_db, scope='function')):
    return SQLExitRepository(db)


@router.get('/animal-options', response_model=list[AnimalSummary])
def options(q: str = Query('',max_length=100), actor=Depends(require_permission('exits:read')), repo=Depends(repository)):
    return repo.options(q.strip())


@router.get('', response_model=ExitPage)
def exits(q: str = Query('',max_length=100), exit_type: ExitType | None = None,
          offset: int = Query(0,ge=0), limit: int = Query(25,ge=1,le=100),
          actor=Depends(require_permission('exits:read')), repo=Depends(repository)):
    return repo.page(q.strip(),exit_type,offset,limit)


@router.get('/animals/{animal_id}/history', response_model=ExitHistory)
def history(animal_id: UUID, actor=Depends(require_permission('exits:read')), repo=Depends(repository)):
    return repo.history(str(animal_id))


@router.post('', response_model=ExitResponse, status_code=201)
def create(data: ExitInput, actor=Depends(require_permission('exits:write')), repo=Depends(repository)):
    return repo.create(data,actor)
