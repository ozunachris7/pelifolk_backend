from fastapi import APIRouter, Depends, Response
from src.features.auth.domain.dto.request.AuthRequest import AuthRequest
from src.features.auth.domain.dto.response.AuthResponse import AuthResponse
from src.features.auth.infrastructure.controllers.LoginController import LoginController
from src.features.auth.infrastructure.dependencies import current_user, get_auth_repository, get_login_use_case
from src.features.users.domain.dto.UserDTO import UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=AuthResponse)
def login(request: AuthRequest, response: Response, use_case=Depends(get_login_use_case)):
    response.headers["Cache-Control"] = "no-store"
    return LoginController.execute(request, use_case)


@router.get("/me", response_model=UserResponse)
def me(user=Depends(current_user)):
    return UserResponse.from_user(user)


@router.post("/logout", status_code=204)
def logout(user=Depends(current_user), repository=Depends(get_auth_repository)):
    repository.revoke_sessions(user.id)
    return Response(status_code=204)
