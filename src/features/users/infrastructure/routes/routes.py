from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.security import hash_password
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.users.application.CreateUserUseCase import CreateUserUseCase
from src.features.users.application.GetAllUsersUseCase import GetAllUsersUseCase
from src.features.users.application.GetUserByIdUseCase import GetUserByIdUseCase
from src.features.users.application.UpdateUserUseCase import UpdateUserUseCase
from src.features.users.application.DeleteUserUseCase import DeleteUserUseCase
from src.features.users.domain.dto.UserDTO import UserCreate, UserUpdate, UserResponse
from src.features.users.infrastructure.adapters.MySQL import MySQLUserRepository

router = APIRouter(prefix="/users", tags=["Users"])


def repository(db: Session = Depends(get_db, scope="function")):
    return MySQLUserRepository(db)


@router.get("", response_model=list[UserResponse])
def list_users(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
               actor=Depends(require_permission("users:read")), repo=Depends(repository)):
    return [UserResponse.from_user(user) for user in GetAllUsersUseCase(repo).execute(offset, limit, actor.id)]


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: UUID, actor=Depends(require_permission("users:read")), repo=Depends(repository)):
    return UserResponse.from_user(GetUserByIdUseCase(repo).execute(str(user_id)))


@router.post("", response_model=UserResponse, status_code=201)
def create_user(request: UserCreate, actor=Depends(require_permission("users:write")), repo=Depends(repository)):
    values = request.model_dump()
    values["role_id"] = str(values["role_id"])
    return UserResponse.from_user(CreateUserUseCase(repo, hash_password).execute(values, actor))


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(user_id: UUID, request: UserUpdate, actor=Depends(require_permission("users:write")),
                repo=Depends(repository)):
    values = request.model_dump(exclude_unset=True)
    if "role_id" in values:
        values["role_id"] = str(values["role_id"])
    return UserResponse.from_user(UpdateUserUseCase(repo, hash_password).execute(str(user_id), values, actor))


@router.delete("/{user_id}", status_code=204)
def deactivate_user(user_id: UUID, actor=Depends(require_permission("users:write")), repo=Depends(repository)):
    DeleteUserUseCase(repo).execute(str(user_id), actor)
    return Response(status_code=204)
