from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.roles.application.ManageRolesUseCase import ManageRolesUseCase
from src.features.roles.domain.dto.RoleDTO import RoleCreate, RoleResponse
from src.features.roles.domain.entities.Role import PERMISSIONS
from src.features.roles.infrastructure.adapters.MySQL import MySQLRoleRepository

router = APIRouter(prefix="/roles", tags=["Roles"])


def use_case(db: Session = Depends(get_db, scope="function")):
    return ManageRolesUseCase(MySQLRoleRepository(db))


@router.get("/permissions", response_model=list[str])
def permissions(actor=Depends(require_permission("roles:read"))):
    return sorted(PERMISSIONS)


@router.get("", response_model=list[RoleResponse])
def list_roles(actor=Depends(require_permission("roles:read")), service=Depends(use_case)):
    return [RoleResponse.from_role(role) for role in service.list()]


@router.post("", response_model=RoleResponse, status_code=201)
def create_role(request: RoleCreate, actor=Depends(require_permission("roles:write")), service=Depends(use_case)):
    return RoleResponse.from_role(service.create(request.name, request.permissions, actor))


@router.put("/{role_id}", response_model=RoleResponse)
def update_role(role_id: UUID, request: RoleCreate, actor=Depends(require_permission("roles:write")),
                service=Depends(use_case)):
    return RoleResponse.from_role(service.update(str(role_id), request.name, request.permissions, actor))


@router.delete("/{role_id}", status_code=204)
def delete_role(role_id: UUID, actor=Depends(require_permission("roles:write")), service=Depends(use_case)):
    service.delete(str(role_id), actor)
    return Response(status_code=204)
