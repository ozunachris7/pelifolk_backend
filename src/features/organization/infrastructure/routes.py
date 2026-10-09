from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.organization.application.manage_organization import ManageOrganization
from src.features.organization.domain.dto import AssignmentInput, EffectiveDate, GroupResponse, LocationInput, LocationResponse, MembershipPage, MembershipResponse, NamedInput, TypeInput, TypeResponse, AnimalOptionPage
from .repository import SQLOrganizationRepository

router = APIRouter(tags=['Organization'])


def repository(db: Session = Depends(get_db, scope='function')):
    return SQLOrganizationRepository(db)


@router.get('/location-types', response_model=list[TypeResponse])
def location_types(actor=Depends(require_permission('locations:read')), repo=Depends(repository)):
    return repo.types()


@router.post('/location-types', response_model=TypeResponse, status_code=201)
def create_type(data: TypeInput, actor=Depends(require_permission('locations:write')), repo=Depends(repository)):
    return repo.create_type(data.name, actor.id)


@router.get('/locations', response_model=list[LocationResponse])
def locations(q: str = Query('', max_length=120), active: bool | None = None,
              actor=Depends(require_permission('locations:read')), repo=Depends(repository)):
    return repo.locations(q.strip(), active)


@router.post('/locations', response_model=LocationResponse, status_code=201)
def create_location(data: LocationInput, actor=Depends(require_permission('locations:write')), repo=Depends(repository)):
    return repo.save_location(data, actor.id)


@router.put('/locations/{location_id}', response_model=LocationResponse)
def update_location(location_id: UUID, data: LocationInput, actor=Depends(require_permission('locations:write')), repo=Depends(repository)):
    return repo.save_location(data, actor.id, str(location_id))


@router.get('/groups', response_model=list[GroupResponse])
def groups(q: str = Query('', max_length=120), active: bool | None = None,
           actor=Depends(require_permission('groups:read')), repo=Depends(repository)):
    return repo.groups(q.strip(), active)


@router.get('/groups/animal-options', response_model=AnimalOptionPage)
def animal_options(q: str = Query('', max_length=100), limit: int = Query(50, ge=1, le=100),
                   actor=Depends(require_permission('groups:write')), repo=Depends(repository)):
    return repo.animal_options(q.strip(), limit)


@router.post('/groups', response_model=GroupResponse, status_code=201)
def create_group(data: NamedInput, actor=Depends(require_permission('groups:write')), repo=Depends(repository)):
    return repo.save_group(data, actor.id)


@router.get('/groups/{group_id}', response_model=GroupResponse)
def group(group_id: UUID, actor=Depends(require_permission('groups:read')), repo=Depends(repository)):
    return repo.group_response(repo.group(str(group_id)))


@router.put('/groups/{group_id}', response_model=GroupResponse)
def update_group(group_id: UUID, data: NamedInput, actor=Depends(require_permission('groups:write')), repo=Depends(repository)):
    return repo.save_group(data, actor.id, str(group_id))


@router.get('/groups/{group_id}/memberships', response_model=MembershipPage)
def memberships(group_id: UUID, current: bool = True, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
                actor=Depends(require_permission('groups:read')), repo=Depends(repository)):
    return repo.memberships(str(group_id), current, offset, limit)


@router.post('/groups/{group_id}/assignments', response_model=list[MembershipResponse], status_code=201)
def assign(group_id: UUID, data: AssignmentInput, actor=Depends(require_permission('groups:write')), repo=Depends(repository)):
    return ManageOrganization(repo).assign(str(group_id), data, actor)


@router.post('/groups/{group_id}/animals/{animal_id}/remove', response_model=MembershipResponse)
def remove(group_id: UUID, animal_id: UUID, data: EffectiveDate, actor=Depends(require_permission('groups:write')), repo=Depends(repository)):
    return ManageOrganization(repo).remove(str(group_id), str(animal_id), data, actor)
