from datetime import date
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,Query
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.feeding.domain.dto import FeedCreateInput,FeedInput,FeedPage,FeedResponse,FeedingInput,FeedingPage,FeedingResponse,PriceInput,PriceResponse,TargetResponse,UnitResponse
from .repository import SQLFeedingRepository

router=APIRouter(prefix='/feeding',tags=['Feeding'])


def repository(db: Session=Depends(get_db,scope='function')):
    return SQLFeedingRepository(db)


@router.get('/units',response_model=list[UnitResponse])
def units(actor=Depends(require_permission('feeding:read')),repo=Depends(repository)):
    return repo.units()


@router.get('/feeds',response_model=FeedPage)
def feeds(q: str=Query('',max_length=100),offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),actor=Depends(require_permission('feeding:read')),repo=Depends(repository)):
    return repo.feeds(q.strip(),offset,limit)


@router.post('/feeds',response_model=FeedResponse,status_code=201)
def add_feed(data: FeedCreateInput,actor=Depends(require_permission('feeding:write')),repo=Depends(repository)):
    return repo.save_feed(data,actor)


@router.put('/feeds/{feed_id}',response_model=FeedResponse)
def edit_feed(feed_id: UUID,data: FeedInput,actor=Depends(require_permission('feeding:write')),repo=Depends(repository)):
    return repo.save_feed(data,actor,str(feed_id))


@router.get('/feeds/{feed_id}/prices',response_model=list[PriceResponse])
def prices(feed_id: UUID,actor=Depends(require_permission('feeding:read')),repo=Depends(repository)):
    return repo.prices(str(feed_id))


@router.post('/feeds/{feed_id}/prices',response_model=PriceResponse,status_code=201)
def add_price(feed_id: UUID,data: PriceInput,actor=Depends(require_permission('feeding:write')),repo=Depends(repository)):
    return repo.add_price(str(feed_id),data,actor)


@router.get('/target-options',response_model=list[TargetResponse])
def targets(kind: Literal['animal','group'],q: str=Query('',max_length=100),actor=Depends(require_permission('feeding:read')),repo=Depends(repository)):
    return repo.options(kind,q.strip())


@router.get('/consumptions',response_model=FeedingPage)
def consumptions(q: str=Query('',max_length=100),animal_id: UUID|None=None,group_id: UUID|None=None,date_from: date|None=None,date_to: date|None=None,offset: int=Query(0,ge=0),limit: int=Query(25,ge=1,le=100),actor=Depends(require_permission('feeding:read')),repo=Depends(repository)):
    if date_from and date_to and date_from>date_to:
        raise ApplicationError('Invalid finance date range',422)
    return repo.page(q.strip(),str(animal_id) if animal_id else None,str(group_id) if group_id else None,date_from,date_to,offset,limit)


@router.post('/consumptions',response_model=FeedingResponse,status_code=201)
def add_consumption(data: FeedingInput,actor=Depends(require_permission('feeding:write')),repo=Depends(repository)):
    return repo.create(data,actor)
